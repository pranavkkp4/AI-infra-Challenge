from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from app.analytics.report import maintenance_report
from app.analytics.taxonomy import mine_candidate_phrases
from app.api.dependencies import get_repository, require_data_access, require_operator_access
from app.api.query_service import (
    asset_detail,
    dashboard_payload,
    incident_detail,
    list_assets,
    list_incidents,
    review_queue,
)
from app.api.schemas import HealthResponse, PipelineRequest, ReviewUpdate
from app.api.search import hybrid_search
from app.config import Settings, get_settings
from app.models.database import CommentRow, PipelineRunRow, ReviewRow, WorkOrderRow
from app.models.repository import DATABASE_WRITE_LOCK, SqlAlchemyRepository
from app.pipeline import run_pipeline

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_data_access)])


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_settings),
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> HealthResponse:
    with repository.session() as session:
        analysis_start, analysis_end = session.execute(
            select(func.min(WorkOrderRow.occurred_at), func.max(WorkOrderRow.occurred_at))
        ).one()
        latest_run = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
    is_demo = bool(latest_run and latest_run.source.lower().endswith("demo"))
    return HealthResponse(
        status="operational",
        database="duckdb",
        demo_mode=is_demo,
        dataset_label="Synthetic Demo Dataset" if is_demo else "Operational Dataset",
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        review_threshold=settings.confidence_review_threshold,
        generated_at=datetime.now(UTC),
    )


@router.get("/dashboard")
def dashboard(repository: SqlAlchemyRepository = Depends(get_repository)) -> dict[str, object]:
    return dashboard_payload(repository)


@router.get("/incidents")
def incidents(
    start_date: date | None = None,
    end_date: date | None = None,
    issue_family: str | None = None,
    department: str | None = None,
    asset: str | None = None,
    confidence: str | None = None,
    recurring_only: bool = False,
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> list[dict[str, object]]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "start_date must not be after end_date")
    results = list_incidents(repository)
    filters = {
        "issue_family": issue_family,
        "department": department,
        "asset_key": asset,
        "confidence_level": confidence,
    }
    for key, value in filters.items():
        if value:
            results = [item for item in results if str(item[key]).lower() == value.lower()]
    if recurring_only:
        results = [item for item in results if item["recurring"]]
    if start_date:
        results = [
            item for item in results if date.fromisoformat(item["last_seen"][:10]) >= start_date
        ]
    if end_date:
        results = [
            item for item in results if date.fromisoformat(item["first_seen"][:10]) <= end_date
        ]
    return results


@router.get("/incidents/{incident_id}")
def get_incident(
    incident_id: str, repository: SqlAlchemyRepository = Depends(get_repository)
) -> dict[str, object]:
    result = incident_detail(repository, incident_id)
    if not result:
        raise HTTPException(404, "Incident not found")
    return result


@router.get("/investigations/{incident_id}")
def investigation(
    incident_id: str, repository: SqlAlchemyRepository = Depends(get_repository)
) -> dict[str, object]:
    result = incident_detail(repository, incident_id)
    if not result:
        raise HTTPException(404, "Investigation not found")
    return result


@router.get("/assets")
def assets(repository: SqlAlchemyRepository = Depends(get_repository)) -> list[dict[str, object]]:
    return list_assets(repository)


@router.get("/assets/{asset_key:path}")
def get_asset(
    asset_key: str, repository: SqlAlchemyRepository = Depends(get_repository)
) -> dict[str, object]:
    result = asset_detail(repository, asset_key)
    if not result:
        raise HTTPException(404, "Asset not found")
    return result


@router.get("/reviews")
def reviews(repository: SqlAlchemyRepository = Depends(get_repository)) -> list[dict[str, object]]:
    return review_queue(repository)


@router.patch("/reviews/{insight_id}")
def update_review(
    insight_id: str,
    update: ReviewUpdate,
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> dict[str, object]:
    with DATABASE_WRITE_LOCK, repository.session() as session:
        row = session.scalar(select(ReviewRow).where(ReviewRow.insight_id == insight_id))
        if not row:
            raise HTTPException(404, "Review not found")
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    return {"status": "updated", "insight_id": insight_id, "decision": update.decision}


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=500),
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> dict[str, object]:
    return hybrid_search(repository, q)


@router.get("/reports/maintenance.md")
def report(repository: SqlAlchemyRepository = Depends(get_repository)) -> Response:
    return Response(
        maintenance_report(repository),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="PM_INSIGHT_REPORT.md"'},
    )


@router.get("/taxonomy/phrases")
def taxonomy(repository: SqlAlchemyRepository = Depends(get_repository)) -> list[dict[str, object]]:
    with repository.session() as session:
        texts = session.scalars(
            select(CommentRow.redacted_text).where(CommentRow.is_meaningful.is_(True))
        ).all()
    return mine_candidate_phrases(list(texts))


@router.post("/pipeline/run")
def rerun_pipeline(
    request: PipelineRequest,
    _: None = Depends(require_operator_access),
    settings: Settings = Depends(get_settings),
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> dict[str, object]:
    source = settings.data_dir / request.source
    if request.source == "raw" and not source.exists():
        raise HTTPException(404, "Private raw dataset directory was not found")
    return run_pipeline(
        source,
        repository,
        settings.embedding_model,
        settings.confidence_review_threshold,
        request.use_semantic_model,
    )
