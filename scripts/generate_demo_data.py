#!/usr/bin/env python3
import argparse
import csv
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

ISSUES = (
    {
        "family": "low_pressure",
        "category": "Water Distribution",
        "department": "Water & Sewer",
        "entity": "VALVE",
        "descriptions": (
            "Low water pressure complaint",
            "Pressure investigation",
            "Service pressure follow-up",
        ),
        "notes": (
            "Resident reports low pressure at service connection.",
            "Crew checked service line; pressure remains below expected range.",
            "Pressure issue returned after previous visit.",
            "Replaced worn valve stem and restored normal pressure.",
        ),
        "cause": "Technician observed a corroded valve stem contributing to restricted flow.",
    },
    {
        "family": "water_leak",
        "category": "Water Distribution",
        "department": "Water & Sewer",
        "entity": "HYDRANT",
        "descriptions": (
            "Water leak investigation",
            "Standing water near asset",
            "Service line follow-up",
        ),
        "notes": (
            "Standing water observed near hydrant flange.",
            "Crew isolated service and found continued seepage.",
            "Leak returned at the same connection.",
            "Replaced flange gasket; no additional leakage observed.",
        ),
        "cause": "Technician confirmed a failed flange gasket at the hydrant connection.",
    },
    {
        "family": "main_break",
        "category": "Water Main",
        "department": "Water & Sewer",
        "entity": "WATER_MAIN",
        "descriptions": (
            "Possible water main break",
            "Roadway water report",
            "Main repair follow-up",
        ),
        "notes": (
            "Heavy water flow surfaced through pavement above the main.",
            "Crew exposed a longitudinal break in the water main.",
            "Temporary clamp is holding; monitor for renewed leakage.",
            "Installed permanent repair sleeve and returned main to service.",
        ),
        "cause": "Longitudinal main break was documented by the excavation crew.",
    },
    {
        "family": "sewer_backup",
        "category": "Wastewater Collection",
        "department": "Water & Sewer",
        "entity": "SEWER_MAIN",
        "descriptions": (
            "Sewer backup report",
            "Collection line inspection",
            "Repeat sewer complaint",
        ),
        "notes": (
            "Sewer backup reported at upstream cleanout.",
            "Crew cleared blockage and restored flow.",
            "Backup recurred after prior cleaning.",
            "Camera inspection documented root intrusion at joint 14.",
        ),
        "cause": "Camera inspection documented root intrusion at joint 14.",
    },
    {
        "family": "pothole",
        "category": "Street Repair",
        "department": "Streets & Traffic",
        "entity": "ROAD_SEGMENT",
        "descriptions": (
            "Pothole complaint",
            "Road surface repair",
            "Repeat pavement defect",
        ),
        "notes": (
            "Pothole measured in the eastbound travel lane.",
            "Crew placed cold patch and reopened lane.",
            "Patch failed and pothole returned after rainfall.",
            "Removed failed material and installed compacted hot-mix patch.",
        ),
        "cause": "Crew documented water infiltration beneath the failed patch.",
    },
    {
        "family": "pavement_damage",
        "category": "Pavement Management",
        "department": "Streets & Traffic",
        "entity": "ROAD_SEGMENT",
        "descriptions": (
            "Pavement cracking",
            "Surface inspection",
            "Recurring asphalt failure",
        ),
        "notes": (
            "Alligator cracking observed across the wheel path.",
            "Crack seal applied to limit water intrusion.",
            "Surface damage expanded beyond prior treatment area.",
            "Scheduled core sampling before selecting rehabilitation treatment.",
        ),
        "cause": "Insufficient evidence to determine the underlying pavement cause.",
    },
    {
        "family": "meter_failure",
        "category": "Meter Services",
        "department": "Water & Sewer",
        "entity": "METER",
        "descriptions": ("Meter read exception", "Meter fault", "Repeat meter failure"),
        "notes": (
            "Meter not reading during scheduled route.",
            "Technician reset endpoint; intermittent readings continued.",
            "Meter failed again during remote read cycle.",
            "Replaced failed register and verified three consecutive reads.",
        ),
        "cause": "Technician confirmed a failed meter register.",
    },
    {
        "family": "hvac_failure",
        "category": "Building Mechanical",
        "department": "Municipal Buildings",
        "entity": "AIR_HANDLER",
        "descriptions": (
            "HVAC temperature complaint",
            "Air handler inspection",
            "Repeat cooling issue",
        ),
        "notes": (
            "Second floor reported no cooling from east-zone air handler.",
            "Reset controller; supply air temperature remained unstable.",
            "Cooling issue returned during afternoon load.",
            "Replaced failed actuator and verified damper travel.",
        ),
        "cause": "Technician confirmed a failed damper actuator.",
    },
    {
        "family": "electrical_issue",
        "category": "Electrical Systems",
        "department": "Electrical Services",
        "entity": "LIGHT_PANEL",
        "descriptions": (
            "Electrical outage",
            "Panel inspection",
            "Recurring lighting fault",
        ),
        "notes": (
            "Lighting circuit lost power in the public corridor.",
            "Breaker reset; circuit current was within rated range.",
            "Circuit tripped again under evening load.",
            "Replaced damaged contactor and verified normal operation.",
        ),
        "cause": "Technician documented heat damage at the lighting contactor.",
    },
)


def generate_demo_data(
    output_dir: Path, seed: int = 42, assets: int = 72
) -> dict[str, int]:
    if assets < 1:
        raise ValueError("assets must be at least 1")
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_orders: list[dict[str, str]] = []
    entities: list[dict[str, str]] = []
    comments: list[dict[str, str]] = []
    work_order_number = 10000
    comment_number = 50000
    for asset_index in range(assets):
        issue = ISSUES[asset_index % len(ISSUES)]
        uid = f"{(asset_index % 24) + 1:04d}"
        event_count = 4 if asset_index < 45 else (2 if asset_index < 60 else 1)
        start = datetime(2022, 1, 1, tzinfo=UTC) + timedelta(
            days=asset_index * 16 + rng.randint(0, 12)
        )
        for event_index in range(event_count):
            work_order_number += 1
            work_order_id = f"WO-{work_order_number}"
            occurred = start + timedelta(days=(0, 12, 48, 103)[event_index])
            description = issue["descriptions"][min(event_index, 2)]
            status = (
                "Closed"
                if event_index == event_count - 1 and event_count > 2
                else "Completed"
            )
            priority = "High" if event_index >= 2 and event_count > 2 else "Normal"
            work_orders.append(
                {
                    "WorkOrderId": work_order_id,
                    "CreatedDate": occurred.isoformat(),
                    "Description": description,
                    "Category": issue["category"],
                    "Department": issue["department"],
                    "Status": status,
                    "Priority": priority,
                }
            )
            entities.append(
                {
                    "WorkOrderId": work_order_id,
                    "EntityType": issue["entity"],
                    "EntityUid": uid,
                    "RelationshipType": "primary",
                    "ApplyToEntity": "false",
                }
            )
            if event_index == 1 and asset_index % 4 == 0:
                entities.append(
                    {
                        "WorkOrderId": work_order_id,
                        "EntityType": "SERVICE_ZONE",
                        "EntityUid": f"ZONE-{asset_index % 8 + 1}",
                        "RelationshipType": "related",
                        "ApplyToEntity": "true",
                    }
                )
            comment_number += 1
            note = issue["notes"][event_index]
            if event_index == 1 and asset_index % 11 == 0:
                note += " Contact Jordan Rivera at 303-555-0182; employee ID EMP-48291."
            if event_index == 2 and asset_index % 3 == 0:
                note += f" {issue['cause']}"
            comments.append(
                {
                    "CommentId": f"C-{comment_number}",
                    "WorkOrderId": work_order_id,
                    "CreatedDate": (occurred + timedelta(hours=3)).isoformat(),
                    "Comment": note,
                    "CommentType": "technician",
                }
            )
            comment_number += 1
            comments.append(
                {
                    "CommentId": f"C-{comment_number}",
                    "WorkOrderId": work_order_id,
                    "CreatedDate": occurred.isoformat(),
                    "Comment": "Dispatched to crew.",
                    "CommentType": "dispatcher",
                }
            )
    # Deliberate invalid and duplicate records exercise validation and job deduplication.
    work_orders.append({**work_orders[0]})
    work_orders.append(
        {
            "WorkOrderId": "WO-INVALID-DATE",
            "CreatedDate": "3025-99-99",
            "Description": "Invalid source row",
            "Category": "Unknown",
            "Department": "Unknown",
            "Status": "Open",
            "Priority": "Normal",
        }
    )
    _write_csv(output_dir / "WORKORDER.csv", work_orders)
    _write_csv(output_dir / "WOENTITY.csv", entities)
    _write_csv(output_dir / "WOCOMMENT.csv", comments)
    return {
        "work_orders": len(work_orders),
        "entities": len(entities),
        "comments": len(comments),
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate CivicOps synthetic municipal data"
    )
    parser.add_argument("--output", type=Path, default=Path("data/demo"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--assets", type=int, default=72)
    arguments = parser.parse_args()
    counts = generate_demo_data(arguments.output, arguments.seed, arguments.assets)
    print(f"Generated Synthetic Demo Dataset: {counts}")
