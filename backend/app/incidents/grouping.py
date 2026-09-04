import hashlib
from collections import Counter
from datetime import datetime, timedelta

from app.data.feature_engineering import resolution_signal
from app.incidents.models import IncidentGroup
from app.models.domain import CandidateMatch, CanonicalWorkOrder


class UnionFind:
    def __init__(self, dates: dict[str, datetime]) -> None:
        identifiers = list(dates)
        self.parent = {identifier: identifier for identifier in identifiers}
        self.first_seen = dates.copy()
        self.last_seen = dates.copy()

    def find(self, identifier: str) -> str:
        while self.parent[identifier] != identifier:
            self.parent[identifier] = self.parent[self.parent[identifier]]
            identifier = self.parent[identifier]
        return identifier

    def union(self, left: str, right: str, max_span_days: int) -> bool:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return True
        first_seen = min(self.first_seen[left_root], self.first_seen[right_root])
        last_seen = max(self.last_seen[left_root], self.last_seen[right_root])
        if last_seen - first_seen > timedelta(days=max_span_days):
            return False
        self.parent[right_root] = left_root
        self.first_seen[left_root] = first_seen
        self.last_seen[left_root] = last_seen
        return True


def group_incidents(
    orders: list[CanonicalWorkOrder],
    matches: list[CandidateMatch],
    threshold: float = 0.67,
    episode_max_span_days: int = 180,
) -> list[IncidentGroup]:
    by_id = {order.work_order_id: order for order in orders}
    graph = UnionFind({identifier: order.date for identifier, order in by_id.items()})
    accepted: list[CandidateMatch] = []
    for match in matches:
        if not (match.same_asset or match.related_asset):
            continue
        left = by_id[match.source_work_order_id]
        right = by_id[match.target_work_order_id]
        if match.weighted_score >= threshold and graph.union(
            left.work_order_id, right.work_order_id, episode_max_span_days
        ):
            accepted.append(match)
    grouped: dict[str, list[CanonicalWorkOrder]] = {}
    for order in orders:
        grouped.setdefault(graph.find(order.work_order_id), []).append(order)
    incidents = [_build_group(group, accepted) for group in grouped.values()]
    return sorted(incidents, key=lambda incident: incident.last_seen, reverse=True)


def _build_group(
    orders: list[CanonicalWorkOrder], accepted_matches: list[CandidateMatch]
) -> IncidentGroup:
    sorted_orders = sorted(orders, key=lambda order: order.date)
    ids = {order.work_order_id for order in orders}
    matches = [
        match
        for match in accepted_matches
        if match.source_work_order_id in ids and match.target_work_order_id in ids
    ]
    asset_counts = Counter(
        asset for order in orders for asset in (order.primary_asset_keys or order.asset_keys)
    )
    issue_counts = Counter(order.issue_family for order in orders)
    department_counts = Counter(order.department for order in orders)
    group_hash = hashlib.sha1("|".join(sorted(ids)).encode()).hexdigest()[:8].upper()
    signals = [resolution_signal(" ".join(order.cleaned_notes)) for order in sorted_orders]
    return IncidentGroup(
        incident_id=f"INC-{group_hash}",
        primary_asset_key=asset_counts.most_common(1)[0][0],
        issue_family=issue_counts.most_common(1)[0][0],
        department=department_counts.most_common(1)[0][0],
        first_seen=sorted_orders[0].date,
        last_seen=sorted_orders[-1].date,
        work_orders=sorted_orders,
        matches=matches,
        recurring=len(orders) > 1,
        resolution_status=_episode_resolution(signals),
    )


def _episode_resolution(signals: list[str]) -> str:
    if not signals:
        return "UNKNOWN"
    if signals[-1] == "RESOLVED":
        return "RESOLVED"
    if signals[-1] == "UNRESOLVED" or "REPAIR_RECORDED" in signals[:-1]:
        return "PERSISTENT"
    return signals[-1]
