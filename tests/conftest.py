import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.api.dependencies import get_repository
from app.main import app
from app.models.repository import SqlAlchemyRepository
from app.pipeline import run_pipeline


@pytest.fixture(scope="session")
def repository(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[SqlAlchemyRepository]:
    database_path = tmp_path_factory.mktemp("database") / "test.duckdb"
    repository = SqlAlchemyRepository(f"duckdb:///{database_path.as_posix()}")
    data_dir = PROJECT_ROOT / "data" / "demo"
    run_pipeline(
        data_dir,
        repository,
        embedding_model="offline",
        review_threshold=0.72,
        prefer_transformer=False,
    )
    yield repository
    repository.engine.dispose()


@pytest.fixture
def client(repository: SqlAlchemyRepository) -> Iterator[TestClient]:
    app.dependency_overrides[get_repository] = lambda: repository
    yield TestClient(app)
    app.dependency_overrides.clear()
