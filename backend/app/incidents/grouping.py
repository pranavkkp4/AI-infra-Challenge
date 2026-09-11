import hashlib
from collections import Counter
from datetime import timedelta

from app.data.feature_engineering import resolution_signal
from app.data.validators import classify_asset
from app.incidents.models import IncidentGroup
from app.models.domain import CandidateMatch, CanonicalWorkOrder, IssueFamily


class UnionFind:
    def __init__(self, orders: dict[str, CanonicalWorkOrder]) -> None:
        dates = {identifier: order.date for identifier, order in orders.items()}
        identifiers = list(dates)
        self.parent = {identifier: identifier for identifier in identifiers}
        self.first_seen = dates.copy()
        self.last_seen = dates.copy()
        self.common_assets = {
            identifier: set(order.primary_asset_keys or order.asset_keys)
            for identifier, order in orders.items()
        }

    def find(self, identifier: str) -> str:
        while self.parent[identifier] != identifier:
            self.parent[identifier] = self.parent[self.parent[identifier]]
            identifier = self.parent[identifier]
        return identifier

    def union(self, left: str, right: str, max_span_days: int) -> bool:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return True
        common_assets = self.common_assets[left_root] & self.common_assets[right_root]
        if not common_assets:
            return False
        first_seen = min(self.first_seen[left_root], self.first_seen[right_root])
        last_seen = max(self.last_seen[left_root], self.last_seen[right_root])
        if last_seen - first_seen > timedelta(days=max_span_days):
            return False
        self.parent[right_root] = left_root
        self.first_seen[left_root] = first_seen
        self.last_seen[left_root] = last_seen
        self.common_assets[left_root] = common_assets
        return True


def group_incidents(
    orders: list[CanonicalWorkOrder],
    matches: list[CandidateMatch],
    threshold: float = 0.67,
    episode_max_span_days: int = 180,
) -> list[IncidentGroup]:
    by_id = {order.work_order_id: order for order in orders}
    graph = UnionFind(by_id)
    accepted: list[CandidateMatch] = []
    for match in matches:
        if not match.same_asset:
            continue
        left = by_id[match.source_work_order_id]
        right = by_id[match.target_work_order_id]
        if left.issue_family != right.issue_family and IssueFamily.UNKNOWN not in {
            left.issue_family,
            right.issue_family,
        }:
            continue
        if not _valid_shared_anchor(left, right, match):
            continue
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
    common_assets = set.intersection(
        *(set(order.primary_asset_keys or order.asset_keys) for order in orders)
    )
    issue_counts = Counter(order.issue_family for order in orders)
    department_counts = Counter(order.department for order in orders)
    group_hash = hashlib.sha1("|".join(sorted(ids)).encode()).hexdigest()[:8].upper()
    signals = [resolution_signal(note) for order in sorted_orders for note in order.cleaned_notes]
    issue_family = issue_counts.most_common(1)[0][0]
    issue_evidence_count = sum(order.issue_family == issue_family for order in orders)
    return IncidentGroup(
        incident_id=f"INC-{group_hash}",
        primary_asset_key=sorted(common_assets)[0],
        issue_family=issue_family,
        department=department_counts.most_common(1)[0][0],
        first_seen=sorted_orders[0].date,
        last_seen=sorted_orders[-1].date,
        work_orders=sorted_orders,
        matches=matches,
        recurring=issue_evidence_count >= 3,
        resolution_status=_episode_resolution(signals),
    )


def _episode_resolution(signals: list[str]) -> str:
    if not signals:
        return "UNKNOWN"
    return signals[-1]


def _valid_shared_anchor(
    left: CanonicalWorkOrder, right: CanonicalWorkOrder, match: CandidateMatch
) -> bool:
    shared = set(left.primary_asset_keys or left.asset_keys) & set(
        right.primary_asset_keys or right.asset_keys
    )
    has_equipment = any(classify_asset(asset.split(":", 1)[0]) == "equipment" for asset in shared)
    return has_equipment or match.same_issue_family
