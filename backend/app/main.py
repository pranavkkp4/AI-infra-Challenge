from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.api.dependencies import get_repository
from app.api.router import router
from app.config import get_settings
from app.models.database import PipelineRunRow, WorkOrderRow
from app.pipeline import run_pipeline


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    repository = get_repository()
    repository.create_schema()
    if settings.demo_mode:
        _migrate_legacy_demo_source(repository, settings.data_dir / "demo")
    with repository.session() as session:
        count = session.scalar(select(func.count()).select_from(WorkOrderRow))
    if not count:
        source = settings.data_dir / ("demo" if settings.demo_mode else "raw")
        run_pipeline(
            source,
            repository,
            settings.embedding_model,
            settings.confidence_review_threshold,
            prefer_transformer=False,
        )
    yield


def _migrate_legacy_demo_source(repository, demo_path: Path) -> None:
    with repository.session() as session:
        latest = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
        if latest is None or latest.source.startswith("demo:"):
            return
        try:
            is_bundled_demo = Path(latest.source).resolve() == demo_path.resolve()
        except OSError:
            is_bundled_demo = False
        if is_bundled_demo:
            latest.source = f"demo:{latest.source}"


app = FastAPI(
    title="CivicOps AI API",
    version="0.1.0",
    description="Explainable infrastructure maintenance intelligence",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
