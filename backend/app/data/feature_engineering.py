from collections import Counter
from datetime import datetime, timedelta

from app.models.domain import CanonicalWorkOrder, IssueFamily, TemporalFeatures

ISSUE_KEYWORDS: dict[IssueFamily, tuple[str, ...]] = {
    IssueFamily.MAIN_BREAK: ("main break", "broken main", "water main burst"),
    IssueFamily.LOW_PRESSURE: ("low pressure", "no pressure", "pressure dropped", "weak flow"),
    IssueFamily.WATER_LEAK: ("water leak", "leaking", "standing water", "service line leak"),
    IssueFamily.SEWER_BACKUP: ("sewer backup", "backed up", "overflowing sewer", "blocked sewer"),
    IssueFamily.POTHOLE: ("pothole", "hole in roadway"),
    IssueFamily.PAVEMENT_DAMAGE: ("pavement", "asphalt", "road crack", "surface failure"),
    IssueFamily.METER_FAILURE: ("meter failed", "meter not reading", "meter fault", "bad meter"),
    IssueFamily.HVAC_FAILURE: ("hvac", "air handler", "no heat", "no cooling", "compressor"),
    IssueFamily.ELECTRICAL_ISSUE: (
        "electrical",
        "power outage",
        "breaker",
        "streetlight",
        "short circuit",
    ),
}

REPAIR_TERMS = ("replaced", "repaired", "patched", "cleared", "reset", "sealed", "installed")
RESOLUTION_TERMS = (
    "resolved",
    "returned to service",
    "no additional complaint",
    "operating normally",
)
CONFLICT_TERMS = ("not resolved", "issue returned", "still leaking", "failed again", "recurring")


def classify_issue(text: str) -> IssueFamily:
    lowered = text.lower()
    matches = {
        family: sum(lowered.count(keyword) for keyword in keywords)
        for family, keywords in ISSUE_KEYWORDS.items()
    }
    family, count = max(matches.items(), key=lambda item: item[1])
    return family if count else IssueFamily.UNKNOWN


def has_repair_signal(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in REPAIR_TERMS)


def resolution_signal(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in CONFLICT_TERMS):
        return "UNRESOLVED"
    if any(term in lowered for term in RESOLUTION_TERMS):
        return "RESOLVED"
    if has_repair_signal(text):
        return "REPAIR_RECORDED"
    return "UNKNOWN"


def engineer_temporal_features(orders: list[CanonicalWorkOrder]) -> dict[str, TemporalFeatures]:
    by_asset: dict[str, list[CanonicalWorkOrder]] = {}
    for order in orders:
        for asset_key in order.asset_keys:
            by_asset.setdefault(asset_key, []).append(order)
    features: dict[str, TemporalFeatures] = {}
    for asset_orders in by_asset.values():
        sorted_orders = sorted(asset_orders, key=lambda order: order.date)
        for index, order in enumerate(sorted_orders):
            prior = sorted_orders[:index]
            same_issue = [item for item in prior if item.issue_family == order.issue_family]
            intervals = [
                (same_issue[position].date - same_issue[position - 1].date).days
                for position in range(1, len(same_issue))
            ]
            features[order.work_order_id] = TemporalFeatures(
                days_since_previous=(order.date - prior[-1].date).days if prior else None,
                incidents_30d=_count_since(prior, order.date, 30),
                incidents_90d=_count_since(prior, order.date, 90),
                incidents_365d=_count_since(prior, order.date, 365),
                recurrence_interval_days=sum(intervals) / len(intervals) if intervals else None,
                previous_repair_attempts=sum(
                    has_repair_signal(" ".join(item.cleaned_notes)) for item in same_issue
                ),
                issue_persistence=min(1.0, len(same_issue) / 4),
            )
    return features


def issue_distribution(orders: list[CanonicalWorkOrder]) -> Counter[IssueFamily]:
    return Counter(order.issue_family for order in orders)


def _count_since(orders: list[CanonicalWorkOrder], date: datetime, days: int) -> int:
    cutoff = date - timedelta(days=days)
    return sum(order.date >= cutoff for order in orders)
