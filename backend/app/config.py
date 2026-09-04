from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIVICOPS_", env_file=".env", extra="ignore")

    app_name: str = "CivicOps AI"
    database_url: str = f"duckdb:///{(PROJECT_ROOT / 'data' / 'civicops.duckdb').as_posix()}"
    data_dir: Path = PROJECT_ROOT / "data"
    demo_mode: bool = True
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    confidence_review_threshold: float = Field(default=0.72, ge=0, le=1)
    llm_provider: str = "deterministic"
    operator_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"


@lru_cache
def get_settings() -> Settings:
    return Settings()
