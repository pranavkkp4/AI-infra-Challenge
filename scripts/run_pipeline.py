#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.models.repository import SqlAlchemyRepository
from app.pipeline import run_pipeline

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the CivicOps intelligence pipeline"
    )
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "demo")
    parser.add_argument(
        "--semantic", action="store_true", help="Use sentence-transformers + FAISS"
    )
    args = parser.parse_args()
    settings = get_settings()
    repository = SqlAlchemyRepository(settings.database_url)
    result = run_pipeline(
        args.source,
        repository,
        settings.embedding_model,
        settings.confidence_review_threshold,
        prefer_transformer=args.semantic,
    )
    print(result)
