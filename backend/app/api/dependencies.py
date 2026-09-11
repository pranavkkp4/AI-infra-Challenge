from functools import lru_cache
from secrets import compare_digest

from fastapi import Depends, Header, HTTPException, Request

from app.api.query_service import is_demo_source, latest_pipeline_run
from app.config import Settings, get_settings
from app.models.repository import SqlAlchemyRepository


@lru_cache
def get_repository() -> SqlAlchemyRepository:
    return SqlAlchemyRepository(get_settings().database_url)


def require_data_access(
    request: Request,
    settings: Settings = Depends(get_settings),
    repository: SqlAlchemyRepository = Depends(get_repository),
    operator_key: str | None = Header(default=None, alias="X-CivicOps-Key"),
) -> None:
    if request.url.path == "/api/v1/health":
        return
    latest_run = latest_pipeline_run(repository)
    source_is_demo = is_demo_source(latest_run.source if latest_run else None)
    if settings.demo_mode and source_is_demo:
        return
    _verify_operator_key(settings, operator_key)


def require_operator_access(
    settings: Settings = Depends(get_settings),
    operator_key: str | None = Header(default=None, alias="X-CivicOps-Key"),
) -> None:
    _verify_operator_key(settings, operator_key)


def _verify_operator_key(settings: Settings, operator_key: str | None) -> None:
    if not settings.operator_api_key:
        raise HTTPException(503, "Operator API key is not configured")
    if not operator_key or not compare_digest(operator_key, settings.operator_api_key):
        raise HTTPException(401, "Valid X-CivicOps-Key header required")
