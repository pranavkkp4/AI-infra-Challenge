import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from app.analytics.report import maintenance_report, maintenance_report_payload
from app.analytics.taxonomy import mine_candidate_phrases
from app.api.dependencies import (
    get_repository,
    operator_access_required,
    require_data_access,
    require_operator_access,
)
from app.api.query_service import (
    asset_detail,
    clear_query_caches,
    dashboard_payload,
    dataset_label,
    incident_detail,
    is_demo_source,
    latest_pipeline_run,
    list_assets,
    list_incidents,
    review_page,
)
from app.api.schemas import HealthResponse, PipelineRequest, ReviewUpdate
from app.api.search import hybrid_search
from app.config import Settings, get_settings
from app.models.database import CommentRow, IncidentRow, InsightRow, ReviewRow
from app.models.repository import DATABASE_WRITE_LOCK, SqlAlchemyRepository
from app.pipeline import _load_configured_calibration, run_pipeline

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_data_access)])


@router.get("/health", response_model=HealthResponse)
def health(
    settings: Settings = Depends(get_settings),
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> HealthResponse:
    with repository.session() as session:
        analysis_start, analysis_end = session.execute(
            select(func.min(IncidentRow.first_seen), func.max(IncidentRow.last_seen))
        ).one()
    latest_run = latest_pipeline_run(repository)
    source = latest_run.source if latest_run else None
    is_demo = is_demo_source(source)
    return HealthResponse(
        status="operational",
        database="duckdb",
        demo_mode=settings.demo_mode and is_demo,
        dataset_label=dataset_label(source),
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        review_threshold=settings.confidence_review_threshold,
        generated_at=datetime.now(UTC),
        llm_provider=settings.llm_provider,
        calibration=_calibration_health(settings, source),
        requires_operator_key=operator_access_required(settings, is_demo),
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
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> dict[str, object]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "start_date must not be after end_date")
    results = list_incidents(repository)
    facets = {
        "issue_families": sorted({str(item["issue_family"]) for item in results}),
        "departments": sorted({str(item["department"]) for item in results}),
    }
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
    return _page(results, limit, offset, facets=facets)


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
def assets(
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    asset_class: Literal["equipment", "location"] | None = None,
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> dict[str, object]:
    results = list_assets(repository)
    if asset_class:
        results = [item for item in results if item["asset_class"] == asset_class]
    return _page(results, limit, offset)


@router.get("/assets/{asset_key:path}")
def get_asset(
    asset_key: str, repository: SqlAlchemyRepository = Depends(get_repository)
) -> dict[str, object]:
    result = asset_detail(repository, asset_key)
    if not result:
        raise HTTPException(404, "Asset not found")
    return result


@router.get("/reviews")
def reviews(
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    decision: Literal["CONFIRMED", "REJECTED", "PENDING"] | None = None,
    insight_id: str | None = None,
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> dict[str, object]:
    items, total = review_page(repository, limit, offset, decision, insight_id)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


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
        if row.archived:
            raise HTTPException(409, "Archived review snapshots are read-only")
        changes = update.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(row, field, value)
        if "edited_issue_family" in changes:
            insight = session.scalar(select(InsightRow).where(InsightRow.insight_id == insight_id))
            if insight is None:
                raise HTTPException(404, "Insight not found")
            incident = session.scalar(
                select(IncidentRow).where(IncidentRow.incident_id == insight.incident_id)
            )
            if incident is None:
                raise HTTPException(404, "Incident not found")
            incident.issue_family = (
                changes["edited_issue_family"] or insight.payload["issue_family"]
            )
        row.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
    clear_query_caches()
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


@router.get("/reports/maintenance.json")
def report_json(
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repository: SqlAlchemyRepository = Depends(get_repository),
) -> Response:
    return Response(
        json.dumps(maintenance_report_payload(repository, limit=limit, offset=offset), indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="PM_INSIGHT_REPORT.json"'},
    )


@router.get("/taxonomy/phrases")
def taxonomy(repository: SqlAlchemyRepository = Depends(get_repository)) -> list[dict[str, object]]:
    with repository.session() as session:
        texts = session.scalars(
            select(CommentRow.redacted_text).where(CommentRow.is_meaningful.is_(True))
        ).all()
    return mine_candidate_phrases(list(texts))


def _page(items: list[dict[str, object]], limit: int, offset: int, **metadata) -> dict[str, object]:
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
        **metadata,
    }


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
    try:
        result = run_pipeline(
            source,
            repository,
            settings.embedding_model,
            settings.confidence_review_threshold,
            request.use_semantic_model,
            settings=settings,
        )
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    clear_query_caches()
    return result


def _calibration_health(settings: Settings, source: str | None) -> dict[str, object]:
    configured = settings.calibration_artifact_path is not None
    try:
        source_dir = _source_dir_from_identity(source, settings)
        source_is_demo = is_demo_source(source)
        if source is not None and settings.demo_mode and not source_is_demo:
            effective_settings = settings.model_copy(update={"demo_mode": False})
        else:
            effective_settings = settings
        artifact = _load_configured_calibration(effective_settings, source_dir)
    except (OSError, ValueError) as error:
        return {"configured": configured, "applied": False, "error": str(error)}
    if artifact is None:
        return {"configured": False, "applied": False, "reason": "No calibration artifact applied."}
    return {"configured": True, **artifact.provenance()}


def _source_dir_from_identity(source: str | None, settings: Settings) -> Path:
    if source is None:
        return settings.data_dir / ("demo" if settings.demo_mode else "raw")
    if source.startswith(("demo:", "starter:", "cityworks:")):
        parts = source.split(":", 2)
        if len(parts) != 3:
            raise ValueError("Pipeline source identity is not manifest-bound")
        if source.startswith("demo:") and not re.fullmatch(r"[0-9a-f]{16}", parts[1]):
            raise ValueError("Pipeline source identity is not manifest-bound")
        return Path(parts[2])
    return Path(source)
