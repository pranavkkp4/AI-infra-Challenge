#!/usr/bin/env python3
"""Label the synthetic audit sample against the fixture's declared contract.

These are reproducible software-validation labels, not human maintenance judgments.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.models.database import (
    IncidentRow,
    IncidentWorkOrderRow,
    InsightRow,
)
from app.models.repository import SqlAlchemyRepository

COMPONENT_FIELDS = (
    "grouping_correct",
    "issue_family_correct",
    "citations_sufficient",
    "interpretation_supported",
    "recommendation_appropriate",
)
LABEL_SOURCE = "synthetic_contract_oracle"
LABEL_POLICY = "fixture-manifest-membership-and-grounding-contract-v1"


def read_rows(source: Path) -> list[dict[str, str]]:
    with source.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def label_rows(
    rows: list[dict[str, str]],
    repository: SqlAlchemyRepository,
    manifest: dict[str, object],
) -> list[dict[str, str]]:
    scenario_by_order = {
        work_order_id: scenario
        for scenario in manifest["scenarios"]
        for work_order_id in scenario["work_order_ids"]
    }
    with repository.session() as session:
        labeled = []
        for row in rows:
            incident = session.get(IncidentRow, row["incident_id"])
            insight = session.scalar(
                select(InsightRow).where(InsightRow.incident_id == row["incident_id"])
            )
            if incident is None or insight is None:
                raise ValueError(
                    f"Audit row references a missing incident: {row['incident_id']}"
                )
            order_ids = set(
                session.scalars(
                    select(IncidentWorkOrderRow.work_order_id).where(
                        IncidentWorkOrderRow.incident_id == incident.incident_id
                    )
                ).all()
            )
            scenarios = {
                json.dumps(scenario_by_order[work_order_id], sort_keys=True)
                for work_order_id in order_ids
                if work_order_id in scenario_by_order
            }
            expected = (
                json.loads(next(iter(scenarios))) if len(scenarios) == 1 else None
            )
            payload = insight.payload
            supporting = set(payload.get("supporting_work_orders", []))
            contradicting = set(payload.get("contradicting_work_orders", []))
            cited = supporting | contradicting
            evidence_by_field = payload.get("evidence_by_field", {})
            field_ids = {
                work_order_id
                for identifiers in evidence_by_field.values()
                for work_order_id in identifiers
            }
            grouping_correct = bool(expected) and order_ids == set(
                expected["work_order_ids"]
            )
            issue_family_correct = (
                bool(expected) and payload["issue_family"] == expected["issue_family"]
            )
            citations_sufficient = (
                bool(supporting) and cited <= order_ids and field_ids <= cited
            )
            interpretation = str(payload.get("interpretation", ""))
            interpretation_supported = (
                bool(evidence_by_field.get("interpretation"))
                and set(evidence_by_field["interpretation"]) <= order_ids
                and "WorkOrderIds:" in interpretation
            )
            action = str(payload.get("recommended_action", ""))
            recommendation_appropriate = (
                bool(action)
                and bool(evidence_by_field.get("recommended_action"))
                and set(evidence_by_field["recommended_action"]) <= cited
                and "Supporting WorkOrderIds:" in action
                and not any(
                    phrase in action.lower()
                    for phrase in (
                        "create a work order",
                        "dispatch now",
                        "authorize work",
                    )
                )
            )
            components = {
                "grouping_correct": int(grouping_correct),
                "issue_family_correct": int(issue_family_correct),
                "citations_sufficient": int(citations_sufficient),
                "interpretation_supported": int(interpretation_supported),
                "recommendation_appropriate": int(recommendation_appropriate),
            }
            failures = [name for name, value in components.items() if not value]
            labeled.append(
                {
                    **row,
                    **{name: str(value) for name, value in components.items()},
                    "actual_correct": str(int(not failures)),
                    "failure_category": failures[0] if failures else "",
                    "reviewer_note": (
                        "Synthetic contract oracle label; not a human maintenance judgment. "
                        + (
                            "Failed: " + ", ".join(failures)
                            if failures
                            else "All contract checks passed."
                        )
                    ),
                    "label_source": LABEL_SOURCE,
                    "label_policy": LABEL_POLICY,
                    "dataset_id": str(manifest["dataset_id"]),
                }
            )
    return labeled


def write_rows(rows: list[dict[str, str]], destination: Path) -> None:
    if not rows:
        raise ValueError("The audit sample is empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Label a synthetic audit sample against its declared fixture contract"
    )
    parser.add_argument("--input", type=Path, default=Path("data/audit_sample.csv"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/audit_sample_labeled.csv")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/demo/manifest.json")
    )
    args = parser.parse_args()
    if not args.manifest.exists():
        parser.error(f"Synthetic manifest not found: {args.manifest}")
    settings = get_settings()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    labeled = label_rows(
        read_rows(args.input),
        SqlAlchemyRepository(settings.database_url),
        manifest,
    )
    write_rows(labeled, args.output)
    print(f"Wrote {len(labeled)} traceable synthetic labels to {args.output}")
