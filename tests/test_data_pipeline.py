import subprocess
import sys
from pathlib import Path

import pytest
from app.data.normalizer import normalize_source
from app.models.database import (
    AssetRow,
    IncidentRow,
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


def test_pipeline_persists_canonical_metrics(repository) -> None:
    with repository.session() as session:
        work_orders = session.scalar(select(func.count()).select_from(WorkOrderRow))
        assets = session.scalar(select(func.count()).select_from(AssetRow))
        incidents = session.scalar(select(func.count()).select_from(IncidentRow))
        reviews = session.scalar(select(func.count()).select_from(ReviewRow))

    assert work_orders == 222
    assert assets == 74
    assert incidents > 0
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
    with repository.session() as session:
        review = session.scalars(select(ReviewRow)).first()
        review.decision = "CONFIRMED"
        review.reviewer_note = "Preserve this decision."
        insight_id = review.insight_id
    run_pipeline(**options)
    with repository.session() as session:
        preserved = session.scalar(
            select(ReviewRow).where(ReviewRow.insight_id == insight_id)
        )
        run_count = session.scalar(select(func.count()).select_from(PipelineRunRow))

    assert preserved.decision == "CONFIRMED"
    assert preserved.reviewer_note == "Preserve this decision."
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
    assert run_count == 3
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
