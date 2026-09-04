from collections import Counter
from datetime import datetime, timedelta

from app.incidents.models import IncidentGroup
from app.models.domain import AssetRisk


def score_asset_risk(asset_key: str, incidents: list[IncidentGroup]) -> AssetRisk:
    evidence = [
        (
            incident.resolution_status,
            [
                (order.date, order.issue_family.value, order.priority)
                for order in incident.work_orders
                if asset_key in (order.primary_asset_keys or order.asset_keys)
            ],
        )
        for incident in incidents
        if any(
            asset_key in (order.primary_asset_keys or order.asset_keys)
            for order in incident.work_orders
        )
    ]
    return score_asset_risk_evidence(asset_key, evidence)


def score_asset_risk_evidence(
    asset_key: str,
    evidence: list[tuple[str, list[tuple[datetime, str, str]]]],
) -> AssetRisk:
    if not evidence:
        return AssetRisk(asset_key=asset_key, score=0, reasons=[], components={})
    orders = [order for _, incident_orders in evidence for order in incident_orders]
    latest_date = max(date for date, _, _ in orders)
    recent_90 = sum(date >= latest_date - timedelta(days=90) for date, _, _ in orders)
    family_counts = Counter(issue_family for _, issue_family, _ in orders)
    repeated = max(family_counts.values()) if family_counts else 0
    unresolved = sum(
        resolution in {"PERSISTENT", "UNKNOWN", "REPAIR_RECORDED"} for resolution, _ in evidence
    )
    high_priority = sum(
        priority.lower() in {"high", "urgent", "emergency"} for _, _, priority in orders
    )
    components = {
        "frequency": min(1, len(orders) / 8),
        "recurrence": min(1, max(0, repeated - 1) / 4),
        "severity": min(1, high_priority / 3),
        "unresolved": min(1, unresolved / 3),
        "recent_density": min(1, recent_90 / 5),
    }
    score = round(
        25 * components["frequency"]
        + 30 * components["recurrence"]
        + 15 * components["severity"]
        + 15 * components["unresolved"]
        + 15 * components["recent_density"]
    )
    reasons = [f"{len(orders)} work orders in the analyzed history"]
    if recent_90:
        reasons.append(f"{recent_90} work orders within its latest 90-day window")
    if repeated > 1:
        reasons.append(f"same issue family repeated {repeated} times")
    if high_priority:
        reasons.append(f"{high_priority} high-priority work orders")
    if unresolved:
        reasons.append(f"{unresolved} episodes lack a confirmed resolution")
    return AssetRisk(asset_key=asset_key, score=score, reasons=reasons, components=components)
