from statistics import mean

from app.incidents.models import IncidentGroup
from app.models.domain import ConfidenceBreakdown, ConfidenceLevel

DEFAULT_WEIGHTS = {
    "semantic_consistency": 0.25,
    "asset_consistency": 0.20,
    "temporal_consistency": 0.15,
    "evidence_strength": 0.20,
    "issue_agreement": 0.20,
}


def score_confidence(
    incident: IncidentGroup,
    review_threshold: float = 0.72,
    weights: dict[str, float] | None = None,
) -> ConfidenceBreakdown:
    chosen = weights or DEFAULT_WEIGHTS
    orders = incident.work_orders
    semantics = [match.semantic_similarity for match in incident.matches]
    semantic = mean(semantics) if semantics else 0.40
    asset = mean(
        incident.primary_asset_key in (order.primary_asset_keys or order.asset_keys)
        for order in orders
    )
    gaps = [(orders[index].date - orders[index - 1].date).days for index in range(1, len(orders))]
    temporal = mean(max(0, 1 - gap / 180) for gap in gaps) if gaps else 0.50
    usable_notes = sum(bool(order.cleaned_notes) for order in orders)
    evidence = min(1.0, 0.35 + usable_notes / max(2, len(orders)) * 0.65)
    issue = mean(order.issue_family == incident.issue_family for order in orders)
    unresolved = sum(
        any(
            term in " ".join(order.cleaned_notes).lower()
            for term in ("not resolved", "issue returned", "again")
        )
        for order in orders
    )
    conflict_penalty = min(0.18, unresolved * 0.04)
    components = {
        "semantic_consistency": semantic,
        "asset_consistency": asset,
        "temporal_consistency": temporal,
        "evidence_strength": evidence,
        "issue_agreement": issue,
    }
    score = sum(chosen[name] * value for name, value in components.items()) - conflict_penalty
    score = max(0.0, min(1.0, score))
    level = (
        ConfidenceLevel.HIGH
        if score >= 0.82
        else (ConfidenceLevel.MEDIUM if score >= 0.65 else ConfidenceLevel.LOW)
    )
    return ConfidenceBreakdown(
        **components,
        conflict_penalty=conflict_penalty,
        score=score,
        level=level,
        requires_human_review=score < review_threshold,
    )
