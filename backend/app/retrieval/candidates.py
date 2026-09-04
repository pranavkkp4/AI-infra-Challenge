from collections import defaultdict
from datetime import timedelta

from app.models.domain import CandidateMatch, CanonicalWorkOrder, IssueFamily
from app.retrieval.embeddings import EmbeddingIndex

DEFAULT_WEIGHTS = {"semantic": 0.35, "asset": 0.30, "temporal": 0.15, "issue": 0.20}


def generate_candidates(
    orders: list[CanonicalWorkOrder],
    model_name: str,
    max_days: int = 365,
    weights: dict[str, float] | None = None,
    prefer_transformer: bool = True,
    blocked_neighbors: int = 12,
) -> tuple[list[CandidateMatch], EmbeddingIndex]:
    if not orders:
        return [], EmbeddingIndex(model_name, prefer_transformer)
    chosen_weights = weights or DEFAULT_WEIGHTS
    by_id = {order.work_order_id: order for order in orders}
    ids = list(by_id)
    texts = [_retrieval_text(by_id[identifier]) for identifier in ids]
    index = EmbeddingIndex(model_name, prefer_transformer).fit(ids, texts)
    candidate_pairs: set[tuple[str, str]] = set()
    _add_blocked_pairs(candidate_pairs, orders, max_days, blocked_neighbors)
    pair_scores = index.similarities_for_pairs(sorted(candidate_pairs))
    matches = [
        _score_pair(
            by_id[left], by_id[right], pair_scores.get((left, right), 0), max_days, chosen_weights
        )
        for left, right in candidate_pairs
        if left in by_id and right in by_id
    ]
    return sorted(
        matches,
        key=lambda match: (
            -match.weighted_score,
            match.source_work_order_id,
            match.target_work_order_id,
        ),
    ), index


def _add_blocked_pairs(
    pairs: set[tuple[str, str]],
    orders: list[CanonicalWorkOrder],
    max_days: int,
    blocked_neighbors: int,
) -> None:
    by_asset: dict[str, list[CanonicalWorkOrder]] = defaultdict(list)
    by_issue: dict[IssueFamily, list[CanonicalWorkOrder]] = defaultdict(list)
    for order in orders:
        for asset in order.asset_keys:
            by_asset[asset].append(order)
        if order.issue_family != IssueFamily.UNKNOWN:
            by_issue[order.issue_family].append(order)
    for bucket in [*by_asset.values(), *by_issue.values()]:
        sorted_bucket = sorted(bucket, key=lambda order: order.date)
        for left_index, left in enumerate(sorted_bucket):
            for right in sorted_bucket[left_index + 1 : left_index + 1 + blocked_neighbors]:
                if right.date - left.date > timedelta(days=max_days):
                    break
                if left.work_order_id != right.work_order_id:
                    pairs.add(tuple(sorted((left.work_order_id, right.work_order_id))))


def _score_pair(
    left: CanonicalWorkOrder,
    right: CanonicalWorkOrder,
    semantic: float,
    max_days: int,
    weights: dict[str, float],
) -> CandidateMatch:
    left_primary = set(left.primary_asset_keys or left.asset_keys)
    right_primary = set(right.primary_asset_keys or right.asset_keys)
    shared_primary = left_primary & right_primary
    shared_assets = set(left.asset_keys) & set(right.asset_keys)
    same_asset = bool(shared_primary)
    related_asset = bool(shared_assets - shared_primary)
    elapsed_days = abs((left.date - right.date).total_seconds()) / 86_400
    days_apart = round(elapsed_days)
    temporal = max(0.0, 1 - elapsed_days / max_days)
    same_issue = (
        left.issue_family == right.issue_family and left.issue_family != IssueFamily.UNKNOWN
    )
    asset_score = 1.0 if same_asset else (0.5 if related_asset else 0.0)
    weighted = (
        weights["semantic"] * semantic
        + weights["asset"] * asset_score
        + weights["temporal"] * temporal
        + weights["issue"] * float(same_issue)
    )
    reasons = []
    if same_asset:
        reasons.append(f"shared asset {sorted(shared_assets)[0]}")
    if related_asset:
        reasons.append("co-attached related asset")
    if same_issue:
        reasons.append(f"same issue family: {left.issue_family.value}")
    reasons.append(f"{days_apart} days apart")
    reasons.append(f"semantic similarity {semantic:.2f}")
    return CandidateMatch(
        source_work_order_id=left.work_order_id,
        target_work_order_id=right.work_order_id,
        semantic_similarity=semantic,
        same_asset=same_asset,
        related_asset=related_asset,
        days_apart=days_apart,
        temporal_score=temporal,
        same_issue_family=same_issue,
        weighted_score=max(0, min(1, weighted)),
        reasons=reasons,
    )


def _retrieval_text(order: CanonicalWorkOrder) -> str:
    return " ".join([order.category, order.description, *order.redacted_notes])
