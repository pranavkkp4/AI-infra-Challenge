import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.alp.intervals import infer_pm_interval
from app.analytics.report import maintenance_report_payload
from app.confidence.engine import score_confidence
from app.config import Settings
from app.evaluation.calibration import (
    fit_calibrator,
    load_calibration_artifact,
    save_calibration_artifact,
)
from app.incidents.models import IncidentGroup
from app.models.domain import CanonicalWorkOrder, IssueFamily
from app.rag.providers import (
    AnthropicProvider,
    DeterministicProvider,
    OllamaProvider,
    create_provider,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _order(identifier: str, date: datetime) -> CanonicalWorkOrder:
    return CanonicalWorkOrder(
        work_order_id=identifier,
        asset_keys=["VALVE:V-1"],
        primary_asset_keys=["VALVE:V-1"],
        date=date,
        category="Water distribution",
        department="WATER",
        cleaned_notes=["Low pressure returned after prior repair."],
        redacted_notes=["Low pressure returned after prior repair."],
        issue_family=IssueFamily.LOW_PRESSURE,
    )


def _incident(orders: list[CanonicalWorkOrder]) -> IncidentGroup:
    return IncidentGroup(
        incident_id="INC-INTERVAL",
        primary_asset_key="VALVE:V-1",
        issue_family=IssueFamily.LOW_PRESSURE,
        department="WATER",
        first_seen=orders[0].date,
        last_seen=orders[-1].date,
        work_orders=orders,
        matches=[],
        recurring=len(orders) >= 3,
        resolution_status="UNRESOLVED",
    )


def test_provider_factory_selects_adapters_and_fails_closed_without_keys() -> None:
    assert isinstance(create_provider(Settings()), DeterministicProvider)
    assert isinstance(
        create_provider(Settings(llm_provider="anthropic", anthropic_api_key="secret")),
        AnthropicProvider,
    )
    assert isinstance(create_provider(Settings(llm_provider="ollama")), OllamaProvider)
    with pytest.raises(ValueError, match="OpenAI provider requires"):
        create_provider(Settings(llm_provider="openai"))


def test_calibration_isotonic_transform_is_monotonic_and_applied_to_confidence() -> (
    None
):
    artifact = fit_calibrator([(0.1, 1), (0.5, 1), (0.9, 1)], source="test-audit")
    assert artifact.transform_scores([0.0, 0.4, 1.0]) == [1.0, 1.0, 1.0]
    orders = [_order("WO-1", datetime(2024, 1, 1, tzinfo=UTC))]
    confidence = score_confidence(_incident(orders), calibration_artifact=artifact)
    assert confidence.score == 1.0
    assert confidence.raw_score is not None and confidence.raw_score < confidence.score
    assert confidence.calibration["artifact_id"] == artifact.artifact_id


def test_calibration_artifact_round_trips_as_versioned_json(tmp_path: Path) -> None:
    artifact = fit_calibrator([(0.1, 0), (0.9, 1)], source="test-audit")
    destination = tmp_path / "calibration.json"
    save_calibration_artifact(artifact, destination)

    loaded = load_calibration_artifact(destination)

    assert loaded.artifact_version == "1.0"
    assert loaded.transform(0.9) == artifact.transform(0.9)


def test_calibration_rejects_an_artifact_trained_on_calibrated_scores() -> None:
    artifact = fit_calibrator([(0.1, 0), (0.9, 1)], source="test-audit").model_copy(
        update={"score_space": "calibrated"}
    )

    with pytest.raises(ValueError, match="raw scores"):
        score_confidence(
            _incident([_order("WO-1", datetime(2024, 1, 1, tzinfo=UTC))]),
            calibration_artifact=artifact,
        )


def test_pm_interval_uses_positive_episode_gaps() -> None:
    orders = [
        _order("WO-1", datetime(2024, 1, 1, tzinfo=UTC)),
        _order("WO-2", datetime(2024, 2, 1, tzinfo=UTC)),
        _order("WO-3", datetime(2024, 3, 2, tzinfo=UTC)),
    ]
    recommendation = infer_pm_interval(_incident(orders))

    assert recommendation.status == "RECOMMENDED"
    assert recommendation.interval_days == 30.5
    assert recommendation.supporting_work_orders == ["WO-1", "WO-2", "WO-3"]


def test_pm_interval_abstains_with_cited_insufficient_evidence() -> None:
    orders = [_order("WO-1", datetime(2024, 1, 1, tzinfo=UTC))]
    recommendation = infer_pm_interval(_incident(orders))

    assert recommendation.status == "INSUFFICIENT_EVIDENCE"
    assert recommendation.interval_days is None
    assert recommendation.abstention_reason
    assert recommendation.supporting_work_orders == ["WO-1"]


def test_report_exports_all_findings_with_interval_and_provenance(repository) -> None:
    payload = maintenance_report_payload(repository)

    assert payload["TOTAL_FINDINGS"] == payload["EXPORTED_FINDINGS"]
    assert payload["TRUNCATED"] is False
    assert payload["CALIBRATION"]["applied"] is True
    assert payload["CALIBRATION"]["synthetic"] is True
    assert payload["FINDINGS"]
    finding = payload["FINDINGS"][0]
    assert finding["SUPPORTING_WORK_ORDERS"]
    assert finding["EVIDENCE"]
    assert finding["PROVENANCE"]["provider"] == "deterministic"
    assert finding["PM_INTERVAL_RECOMMENDATION"]["status"] in {
        "RECOMMENDED",
        "INSUFFICIENT_EVIDENCE",
    }


@pytest.mark.parametrize(
    "script", ["run_pipeline.py", "sample_audit.py", "evaluate_audit.py"]
)
def test_scripts_help_runs_from_repository_root(script: str) -> None:
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "usage:" in result.stdout.lower()
