from datetime import UTC, datetime, timedelta

import pytest
from app.analytics.taxonomy import mine_candidate_phrases
from app.data.cleaner import clean_comment
from app.data.pii import redact_pii
from app.incidents.grouping import group_incidents
from app.models.domain import (
    CandidateMatch,
    CanonicalWorkOrder,
    IssueFamily,
    MaintenanceInsight,
)
from app.rag.grounding import GroundingError, enforce_grounding
from app.retrieval.candidates import generate_candidates


def _order(identifier: str, month: int, day: int) -> CanonicalWorkOrder:
    return CanonicalWorkOrder(
        work_order_id=identifier,
        asset_keys=["VALVE:V-1"],
        date=datetime(2024, month, day, tzinfo=UTC),
        category="Water distribution",
        department="Water",
        cleaned_notes=["Low pressure returned after prior repair."],
        redacted_notes=["Low pressure returned after prior repair."],
        issue_family=IssueFamily.LOW_PRESSURE,
    )


def _match(left: str, right: str) -> CandidateMatch:
    return CandidateMatch(
        source_work_order_id=left,
        target_work_order_id=right,
        semantic_similarity=0.9,
        same_asset=True,
        days_apart=120,
        temporal_score=0.8,
        same_issue_family=True,
        weighted_score=0.9,
        reasons=["shared asset VALVE:V-1"],
    )


def test_grouping_prevents_transitive_episode_span_overflow() -> None:
    orders = [_order("WO-1", 1, 1), _order("WO-2", 5, 1), _order("WO-3", 9, 1)]
    matches = [_match("WO-1", "WO-2"), _match("WO-2", "WO-3")]

    incidents = group_incidents(
        orders, matches, threshold=0.67, episode_max_span_days=180
    )

    assert sorted(len(incident.work_orders) for incident in incidents) == [1, 2]
    assert all(
        (incident.last_seen - incident.first_seen).days <= 180 for incident in incidents
    )


def test_grouping_never_merges_unrelated_assets_from_text_similarity() -> None:
    first = _order("WO-1", 1, 1)
    second = _order("WO-2", 1, 2).model_copy(
        update={"asset_keys": ["VALVE:V-2"], "primary_asset_keys": ["VALVE:V-2"]}
    )
    semantic_only = _match("WO-1", "WO-2").model_copy(
        update={"same_asset": False, "related_asset": False, "weighted_score": 0.99}
    )

    incidents = group_incidents([first, second], [semantic_only], threshold=0.67)

    assert [len(incident.work_orders) for incident in incidents] == [1, 1]


def test_temporal_scoring_is_symmetric_for_subday_differences() -> None:
    first = _order("WO-Z", 1, 1)
    second = _order("WO-A", 1, 1).model_copy(
        update={"date": first.date + timedelta(hours=1)}
    )

    matches, _ = generate_candidates(
        [first, second], "offline", prefer_transformer=False
    )

    assert matches[0].days_apart == 0
    assert matches[0].temporal_score == pytest.approx(1 - (1 / 24) / 365)


def test_grouping_rejects_fractional_day_span_overflow() -> None:
    first = _order("WO-1", 1, 1)
    late = _order("WO-2", 1, 1).model_copy(
        update={"date": first.date + timedelta(days=180, hours=1)}
    )

    incidents = group_incidents(
        [first, late], [_match("WO-1", "WO-2")], episode_max_span_days=180
    )

    assert [len(incident.work_orders) for incident in incidents] == [1, 1]


def test_pii_is_redacted_and_boilerplate_is_removed() -> None:
    result = redact_pii(
        "Contact Jordan Rivera at 303-555-0182 or jordan@example.gov; employee ID EMP-48291."
    )

    assert result.was_redacted
    assert "303-555-0182" not in result.text
    assert "jordan@example.gov" not in result.text
    assert "EMP-48291" not in result.text
    assert "Jordan Rivera" not in result.text
    assert clean_comment("Dispatched to crew.") == ""


def test_grounding_rejects_citations_outside_retrieved_evidence() -> None:
    insight = MaintenanceInsight.model_construct(
        supporting_work_orders=["WO-1", "WO-OUTSIDE"],
        contradicting_work_orders=[],
    )

    with pytest.raises(GroundingError, match="WO-OUTSIDE"):
        enforce_grounding(insight, {"WO-1"})


def test_candidate_generation_is_bounded_and_deterministic() -> None:
    orders = [
        _order(f"WO-{index:03d}", 1 + index // 27, 1 + index % 27)
        for index in range(40)
    ]

    first, _ = generate_candidates(orders, "offline", prefer_transformer=False)
    second, _ = generate_candidates(orders, "offline", prefer_transformer=False)

    assert len(first) < len(orders) * (len(orders) - 1) / 2
    assert all(item.source_work_order_id != item.target_work_order_id for item in first)
    assert [item.model_dump() for item in first] == [
        item.model_dump() for item in second
    ]


def test_latest_repair_is_not_marked_persistent() -> None:
    first = _order("WO-1", 1, 1)
    repaired = _order("WO-2", 2, 1).model_copy(
        update={"cleaned_notes": ["Crew replaced the valve assembly."]}
    )

    incident = group_incidents(
        [first, repaired], [_match("WO-1", "WO-2")], threshold=0.67
    )[0]

    assert incident.resolution_status == "REPAIR_RECORDED"


def test_taxonomy_handles_stop_word_only_corpus() -> None:
    assert mine_candidate_phrases(["the and or", "the and or"]) == []
