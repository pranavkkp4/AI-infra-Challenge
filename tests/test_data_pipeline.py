import json
import subprocess
import sys
from pathlib import Path

import pytest
from app.api.query_service import is_demo_source, list_incidents, review_page
from app.config import get_settings
from app.data.normalizer import normalize_source
from app.evaluation.calibration import CalibrationArtifact, save_calibration_artifact
from app.main import _migrate_legacy_demo_source
from app.models.database import (
    AssetRow,
    IncidentRow,
    InsightRow,
    PipelineRunRow,
    ReviewRow,
    WorkOrderRow,
)
from app.models.repository import SqlAlchemyRepository
from app.pipeline import run_pipeline
from sqlalchemy import func, select

from scripts.generate_demo_data import generate_demo_data

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


def test_normalization_deduplicates_and_validates_work_orders() -> None:
    dataset = normalize_source(DEMO_DIR)
    identifiers = [order.work_order_id for order in dataset.work_orders]

    assert dataset.report.source_rows["WORKORDER.csv"] == 224
    assert dataset.report.rejected_rows["work_orders"] == 2
    assert len(identifiers) == len(set(identifiers)) == 222
    assert all(
        ":" in asset for order in dataset.work_orders for asset in order.asset_keys
    )


def test_demo_manifest_declares_reproducible_scenarios() -> None:
    manifest = json.loads((DEMO_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["dataset_id"]
    assert len(manifest["scenarios"]) == 72
    assert manifest["scenarios"][0]["work_order_ids"] == [
        "WO-10001",
        "WO-10002",
        "WO-10003",
        "WO-10004",
    ]


def test_pipeline_persists_canonical_metrics(repository) -> None:
    with repository.session() as session:
        work_orders = session.scalar(select(func.count()).select_from(WorkOrderRow))
        assets = session.scalar(select(func.count()).select_from(AssetRow))
        incidents = session.scalar(select(func.count()).select_from(IncidentRow))
        recurring = session.scalar(
            select(func.count()).select_from(IncidentRow).where(IncidentRow.recurring)
        )
        reviews = session.scalar(select(func.count()).select_from(ReviewRow))

    assert work_orders == 222
    assert assets == 74
    assert incidents > 0
    assert recurring > 0
    assert reviews > 0


def test_demo_generator_requires_an_asset(tmp_path) -> None:
    output_dir = tmp_path / "empty-demo"

    with pytest.raises(ValueError, match="assets must be at least 1"):
        generate_demo_data(output_dir, assets=0)

    assert not output_dir.exists()


def test_pipeline_rerun_preserves_reviews_and_run_history(tmp_path) -> None:
    repository = SqlAlchemyRepository(
        f"duckdb:///{(tmp_path / 'rerun.duckdb').as_posix()}"
    )
    options = {
        "source_dir": DEMO_DIR,
        "repository": repository,
        "embedding_model": "offline",
        "review_threshold": 0.72,
        "prefer_transformer": False,
    }
    run_pipeline(**options)
    initial_incident_count = len(list_incidents(repository))
    with repository.session() as session:
        review = session.scalars(select(ReviewRow)).first()
        review.decision = "CONFIRMED"
        review.reviewer_note = "Preserve this decision."
        review.edited_issue_family = "pothole"
        insight_id = review.insight_id
        incident_id = session.get(InsightRow, insight_id).incident_id
    run_pipeline(**options)
    with repository.session() as session:
        preserved = session.scalar(
            select(ReviewRow).where(ReviewRow.insight_id == insight_id)
        )
        run_count = session.scalar(select(func.count()).select_from(PipelineRunRow))
        incident = session.get(IncidentRow, incident_id)

    assert preserved.decision == "CONFIRMED"
    assert preserved.reviewer_note == "Preserve this decision."
    assert preserved.edited_issue_family == "pothole"
    assert incident.issue_family == "pothole"
    assert run_count == 2

    reduced_source = tmp_path / "reduced"
    subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "generate_demo_data.py"
            ),
            "--output",
            str(reduced_source),
            "--assets",
            "1",
        ],
        check=True,
    )
    run_pipeline(**{**options, "source_dir": reduced_source})
    with repository.session() as session:
        archived = session.scalar(
            select(ReviewRow).where(ReviewRow.insight_id == insight_id)
        )
        run_count = session.scalar(select(func.count()).select_from(PipelineRunRow))

    assert archived.decision == "CONFIRMED"
    assert archived.archived is True
    assert archived.snapshot["incident"]["incident_id"] == incident_id
    archived_items, _ = review_page(repository, 10, 0, insight_id=insight_id)
    assert archived_items[0]["archived"] is True
    assert archived_items[0]["incident"]["incident_id"] == incident_id
    assert run_count == 3
    assert len(list_incidents(repository)) != initial_incident_count
    repository.engine.dispose()


def test_pipeline_rerun_removes_pending_reviews_cleared_by_calibration(
    tmp_path,
) -> None:
    database_url = f"duckdb:///{(tmp_path / 'calibration.duckdb').as_posix()}"
    repository = SqlAlchemyRepository(database_url)
    options = {
        "source_dir": DEMO_DIR,
        "repository": repository,
        "embedding_model": "offline",
        "review_threshold": 0.72,
        "prefer_transformer": False,
    }
    initial = run_pipeline(**options)
    assert initial["review_queue"] > 0

    artifact_path = tmp_path / "calibration.json"
    save_calibration_artifact(
        CalibrationArtifact(
            artifact_id="test-all-high",
            source="test",
            dataset_id="test-dataset",
            sample_count=1,
            x_values=[0.0],
            y_values=[1.0],
        ),
        artifact_path,
    )
    settings = get_settings().model_copy(
        update={
            "database_url": database_url,
            "demo_mode": False,
            "calibration_enabled": True,
            "calibration_artifact_path": artifact_path,
            "calibration_dataset_id": "test-dataset",
        }
    )
    run_pipeline(**options, settings=settings)

    with repository.session() as session:
        pending = session.scalar(
            select(func.count())
            .select_from(ReviewRow)
            .where(ReviewRow.decision == "PENDING")
        )

    assert pending == 0
    repository.engine.dispose()


def test_legacy_bundled_demo_source_is_migrated(repository) -> None:
    with repository.session() as session:
        latest = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
        latest.source = str(DEMO_DIR)

    _migrate_legacy_demo_source(repository, DEMO_DIR)

    with repository.session() as session:
        latest = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
        assert latest.source.startswith("demo:")
        assert is_demo_source(latest.source)
        latest.source = f"demo:{DEMO_DIR}"

    assert not is_demo_source(f"demo:{DEMO_DIR}")

    _migrate_legacy_demo_source(repository, DEMO_DIR)

    with repository.session() as session:
        latest = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
        assert latest.source.startswith(
            f"demo:{json.loads((DEMO_DIR / 'manifest.json').read_text())['dataset_id']}:"
        )


def test_non_demo_source_requires_calibration_even_in_demo_settings(tmp_path) -> None:
    repository = SqlAlchemyRepository(
        f"duckdb:///{(tmp_path / 'uncalibrated.duckdb').as_posix()}"
    )
    settings = get_settings().model_copy(
        update={
            "demo_mode": True,
            "calibration_artifact_path": None,
            "calibration_enabled": False,
        }
    )

    with pytest.raises(ValueError, match="explicit manual calibration artifact"):
        run_pipeline(
            tmp_path / "raw",
            repository,
            embedding_model="offline",
            review_threshold=0.72,
            prefer_transformer=False,
            settings=settings,
        )
    repository.engine.dispose()


def test_pipeline_replacement_rolls_back_on_write_failure(
    tmp_path, monkeypatch
) -> None:
    repository = SqlAlchemyRepository(
        f"duckdb:///{(tmp_path / 'rollback.duckdb').as_posix()}"
    )
    options = {
        "source_dir": DEMO_DIR,
        "repository": repository,
        "embedding_model": "offline",
        "review_threshold": 0.72,
        "prefer_transformer": False,
    }
    run_pipeline(**options)

    def fail_write(*_args) -> None:
        raise RuntimeError("forced snapshot failure")

    monkeypatch.setattr("app.pipeline._write_incidents", fail_write)
    with pytest.raises(RuntimeError, match="forced snapshot failure"):
        run_pipeline(**options)
    with repository.session() as session:
        work_orders = session.scalar(select(func.count()).select_from(WorkOrderRow))
        run_count = session.scalar(select(func.count()).select_from(PipelineRunRow))

    assert work_orders == 222
    assert run_count == 1
    repository.engine.dispose()
