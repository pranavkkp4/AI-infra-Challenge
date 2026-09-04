#!/usr/bin/env python3
import argparse
import csv
import json
import random
from pathlib import Path

from app.config import get_settings
from app.models.database import IncidentRow, InsightRow
from app.models.repository import SqlAlchemyRepository
from sqlalchemy import select


def sample_rows(
    repository: SqlAlchemyRepository, sample_size: int, seed: int
) -> list[dict[str, object]]:
    with repository.session() as session:
        rows = session.execute(
            select(IncidentRow, InsightRow).join(
                InsightRow, IncidentRow.incident_id == InsightRow.incident_id
            )
        ).all()
    rng = random.Random(seed)
    selected = rng.sample(rows, min(sample_size, len(rows)))
    return [
        {
            "incident_id": incident.incident_id,
            "asset_key": incident.primary_asset_key,
            "issue_family": incident.issue_family,
            "confidence": round(incident.confidence, 6),
            "work_order_count": incident.work_order_count,
            "supporting_work_orders": json.dumps(
                insight.payload["supporting_work_orders"]
            ),
            "actual_correct": "",
            "reviewer_note": "",
        }
        for incident, insight in selected
    ]


def write_sample(rows: list[dict[str, object]], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a deterministic incident audit sample"
    )
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data/audit_sample.csv"))
    args = parser.parse_args()
    if args.size < 1:
        parser.error("--size must be positive")
    settings = get_settings()
    sample = sample_rows(
        SqlAlchemyRepository(settings.database_url), args.size, args.seed
    )
    if not sample:
        parser.error("No persisted incidents found; run scripts/run_pipeline.py first")
    write_sample(sample, args.output)
    print(f"Wrote {len(sample)} rows to {args.output}")
