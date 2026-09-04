from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.api.dependencies import get_repository
from app.api.router import router
from app.config import get_settings
from app.models.database import WorkOrderRow
from app.pipeline import run_pipeline


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    repository = get_repository()
    repository.create_schema()
    with repository.session() as session:
        count = session.scalar(select(func.count()).select_from(WorkOrderRow))
    if not count:
        run_pipeline(
            settings.data_dir / "demo",
            repository,
            settings.embedding_model,
            settings.confidence_review_threshold,
            prefer_transformer=False,
        )
    yield


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
