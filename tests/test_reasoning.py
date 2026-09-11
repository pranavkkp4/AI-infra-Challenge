from datetime import UTC, datetime, timedelta

import pytest
from app.alp.engine import generate_insight
from app.alp.triggers import direct_cause_sentence
from app.analytics.taxonomy import mine_candidate_phrases
from app.confidence.engine import score_confidence
from app.data.cleaner import clean_comment, is_maintenance_comment
from app.data.feature_engineering import classify_issue_with_evidence, resolution_signal
from app.data.pii import redact_external_identifiers, redact_pii
from app.incidents.grouping import group_incidents
from app.models.domain import (
    CandidateMatch,
    CanonicalWorkOrder,
    IssueFamily,
    MaintenanceInsight,
)
from app.rag.grounding import GroundingError, enforce_grounding
from app.rag.prompts import build_evidence_prompt
from app.rag.providers import LLMProvider
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


def test_grouping_never_merges_primary_assets_through_shared_context() -> None:
    first = _order("WO-1", 1, 1).model_copy(
        update={
            "asset_keys": ["PUMP:1", "ADDRESSES:1"],
            "primary_asset_keys": ["PUMP:1"],
        }
    )
    second = _order("WO-2", 1, 2).model_copy(
        update={
            "asset_keys": ["PUMP:2", "ADDRESSES:1"],
            "primary_asset_keys": ["PUMP:2"],
        }
    )
    context_match = _match("WO-1", "WO-2").model_copy(
        update={"same_asset": False, "related_asset": True, "weighted_score": 0.99}
    )

    incidents = group_incidents([first, second], [context_match])

    assert [len(incident.work_orders) for incident in incidents] == [1, 1]


def test_grouping_requires_one_primary_asset_across_the_full_component() -> None:
    bridge = _order("WO-1", 1, 1).model_copy(
        update={
            "asset_keys": ["PUMP:1", "PUMP:2"],
            "primary_asset_keys": ["PUMP:1", "PUMP:2"],
        }
    )
    first = _order("WO-2", 1, 2).model_copy(
        update={"asset_keys": ["PUMP:1"], "primary_asset_keys": ["PUMP:1"]}
    )
    second = _order("WO-3", 1, 3).model_copy(
        update={"asset_keys": ["PUMP:2"], "primary_asset_keys": ["PUMP:2"]}
    )

    incidents = group_incidents(
        [bridge, first, second], [_match("WO-1", "WO-2"), _match("WO-1", "WO-3")]
    )

    assert sorted(len(incident.work_orders) for incident in incidents) == [1, 2]


def test_grouping_rejects_different_known_families() -> None:
    pressure = _order("WO-1", 1, 1)
    leak = _order("WO-2", 1, 2).model_copy(
        update={"issue_family": IssueFamily.WATER_LEAK}
    )
    mixed_match = _match("WO-1", "WO-2").model_copy(update={"same_issue_family": False})

    incidents = group_incidents([pressure, leak], [mixed_match])

    assert [len(incident.work_orders) for incident in incidents] == [1, 1]


def test_recurrence_requires_three_orders_supporting_the_selected_family() -> None:
    orders = [
        _order("WO-1", 1, 1),
        _order("WO-2", 1, 2),
        _order("WO-3", 1, 3).model_copy(update={"issue_family": IssueFamily.UNKNOWN}),
    ]
    mixed_match = _match("WO-2", "WO-3").model_copy(update={"same_issue_family": False})

    incident = group_incidents(orders, [_match("WO-1", "WO-2"), mixed_match])[0]

    assert len(incident.work_orders) == 3
    assert not incident.recurring


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
    assert "Moore, Cynthia" not in redact_pii("By Moore, Cynthia: inspected valve").text
    assert "jane doe" not in redact_pii("Reported by jane doe").text
    assert "(303)555-0182" not in redact_pii("Call (303)555-0182").text
    assert (
        redact_pii("Jordan Rivera's office has a leaking valve").text
        == "[PERSON_REDACTED]'s office has a leaking valve"
    )
    assert not redact_pii("Second-floor office ceiling tile").was_redacted
    assert clean_comment("Dispatched to crew.") == ""
    scaffold = (
        "From: Request ID: 100 WATER PROBLEM Water main/line break/leak/pressure, "
        "meter problem\nProblem Details: Low pressure at hydrant."
    )
    assert clean_comment(scaffold) == "Low pressure at hydrant."
    assert not is_maintenance_comment(
        "JANITORIAL SUPPLIES FM - Janitorial Supply Order"
    )


def test_external_redaction_removes_addresses_without_changing_operator_notes() -> None:
    note = "Checked valve at 123 North Main Street near the hydrant."
    assert not redact_pii(note).was_redacted
    result = redact_external_identifiers(note)
    assert result.was_redacted
    assert "123 North Main Street" not in result.text
    assert "ADDRESS" in result.entity_types

    order = _order("WO-1", 1, 1).model_copy(update={"redacted_notes": [note]})
    prompt = build_evidence_prompt(group_incidents([order], [])[0])
    assert "123 North Main Street" not in prompt
    assert "[ADDRESS_REDACTED]" in prompt

    sensitive = "Meet at 15th & Kelly, PO Box 42, room 203, 39.7392, -104.9903."
    sanitized = redact_external_identifiers(sensitive).text
    assert "15th & Kelly" not in sanitized
    assert "PO Box 42" not in sanitized
    assert "room 203" not in sanitized
    assert "39.7392" not in sanitized
    assert not redact_external_identifiers(
        "Water and Sewer crews coordinated."
    ).was_redacted


class _ExternalProviderProbe(LLMProvider):
    async def _synthesize(self, system: str, evidence: str):
        raise AssertionError("PII-bearing evidence reached the provider")


class _UngroundedProviderProbe(LLMProvider):
    async def _synthesize(self, system: str, evidence: str):
        return MaintenanceInsight.model_construct(
            supporting_work_orders=["WO-OUTSIDE"], contradicting_work_orders=[]
        )


@pytest.mark.asyncio
async def test_external_provider_fails_closed_on_detectable_pii() -> None:
    with pytest.raises(ValueError, match="PII or location identifiers"):
        await _ExternalProviderProbe().synthesize(
            "Grounded system", "Reported by jane doe"
        )
    with pytest.raises(ValueError, match="PII or location identifiers"):
        await _ExternalProviderProbe().synthesize(
            "Grounded system", "Checked equipment at 123 North Main Street."
        )


@pytest.mark.asyncio
async def test_external_provider_enforces_citation_grounding() -> None:
    with pytest.raises(GroundingError, match="WO-OUTSIDE"):
        await _UngroundedProviderProbe().synthesize(
            "Use only supplied evidence.",
            "WORK ORDER: WO-1\nTECHNICIAN NOTE: Valve inspected.",
        )


@pytest.mark.parametrize(
    ("text", "family"),
    [
        ("Crew found a busted water line under the road.", IssueFamily.MAIN_BREAK),
        ("The street light keeps flickering after dark.", IssueFamily.ELECTRICAL_ISSUE),
        ("The air conditioner is blowing warm air.", IssueFamily.HVAC_FAILURE),
    ],
)
def test_corpus_trigger_retrieval_matches_crew_paraphrases(text, family) -> None:
    result = classify_issue_with_evidence(text)

    assert result.family == family
    assert result.trigger
    assert result.score >= 0.18


@pytest.mark.parametrize(
    ("text", "family"),
    [
        ("recurring sewer backups", IssueFamily.SEWER_BACKUP),
        ("streetlights out", IssueFamily.ELECTRICAL_ISSUE),
    ],
)
def test_corpus_trigger_retrieval_accepts_plural_operator_queries(text, family) -> None:
    assert classify_issue_with_evidence(text).family == family


def test_grounding_rejects_citations_outside_retrieved_evidence() -> None:
    insight = MaintenanceInsight.model_construct(
        supporting_work_orders=["WO-1", "WO-OUTSIDE"],
        contradicting_work_orders=[],
    )

    with pytest.raises(GroundingError, match="WO-OUTSIDE"):
        enforce_grounding(insight, {"WO-1"})


def test_grounding_rejects_claims_without_field_evidence_mapping() -> None:
    incident = group_incidents([_order("WO-1", 1, 1)], [])[0]
    insight = generate_insight(incident, score_confidence(incident))
    evidence_by_field = {**insight.evidence_by_field, "summary": []}

    with pytest.raises(GroundingError, match="Claim field summary"):
        enforce_grounding(
            insight.model_copy(update={"evidence_by_field": evidence_by_field}),
            {"WO-1"},
        )


def test_grounding_accepts_numeric_cityworks_work_order_ids() -> None:
    incident = group_incidents([_order("100", 1, 1)], [])[0]
    insight = generate_insight(incident, score_confidence(incident))

    enforce_grounding(insight, {"100"})


def test_candidate_generation_is_bounded_and_deterministic() -> None:
    orders = [
        _order(f"WO-{index:03d}", 1 + index // 27, 1 + index % 27).model_copy(
            update={
                "asset_keys": [f"VALVE:V-{index}"],
                "primary_asset_keys": [f"VALVE:V-{index}"],
            }
        )
        for index in range(40)
    ]

    first, _ = generate_candidates(orders, "offline", prefer_transformer=False)
    second, _ = generate_candidates(orders, "offline", prefer_transformer=False)

    assert len(first) < len(orders) * (len(orders) - 1) / 2
    assert all(item.source_work_order_id != item.target_work_order_id for item in first)
    assert [item.model_dump() for item in first] == [
        item.model_dump() for item in second
    ]


def test_recurrence_requires_three_linked_work_orders() -> None:
    orders = [_order("WO-1", 1, 1), _order("WO-2", 2, 1), _order("WO-3", 3, 1)]

    two_order_incident = group_incidents(orders[:2], [_match("WO-1", "WO-2")])[0]
    three_order_incident = group_incidents(
        orders, [_match("WO-1", "WO-2"), _match("WO-2", "WO-3")]
    )[0]

    assert not two_order_incident.recurring
    assert three_order_incident.recurring


def test_latest_unknown_note_does_not_infer_persistence() -> None:
    repaired = _order("WO-1", 1, 1).model_copy(
        update={"cleaned_notes": ["Crew replaced the valve assembly."]}
    )
    follow_up = _order("WO-2", 2, 1).model_copy(
        update={"cleaned_notes": ["Crew inspected the site."]}
    )

    incident = group_incidents([repaired, follow_up], [_match("WO-1", "WO-2")])[0]

    assert incident.resolution_status == "UNKNOWN"


def test_resolution_terms_use_whole_phrases_and_conflict_precedence() -> None:
    assert resolution_signal("Dispatched to crew for follow-up.") == "UNKNOWN"
    assert (
        resolution_signal("Repair work completed; unit working properly.") == "RESOLVED"
    )
    assert resolution_signal("Unit running but not cooling.") == "UNRESOLVED"
    assert resolution_signal("Patching completed.") == "REPAIR_RECORDED"
    assert resolution_signal("No problem found.") == "NO_ISSUE_OBSERVED"


def test_supported_cause_rejects_negation_and_cites_its_work_order() -> None:
    assert direct_cause_sentence(["Leak was not due to valve failure."]) is None
    assert direct_cause_sentence(["Work was delayed due to weather."]) is None
    order = _order("WO-CAUSE", 1, 1).model_copy(
        update={
            "cleaned_notes": ["Failure was caused by a cracked seal."],
            "redacted_notes": ["Failure was caused by a cracked seal."],
        }
    )
    incident = group_incidents([order], [])[0]

    insight = generate_insight(incident, score_confidence(incident))

    assert insight.possible_cause.support_level.value == "SUPPORTED"
    assert "WorkOrderId: WO-CAUSE" in insight.possible_cause.statement


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
