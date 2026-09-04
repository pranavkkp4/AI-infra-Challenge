import re
from collections import Counter

from sqlalchemy import select

from app.api.query_service import list_assets
from app.data.feature_engineering import classify_issue
from app.models.database import IncidentRow, InsightRow, ReviewRow, WorkOrderRow
from app.models.repository import SqlAlchemyRepository
from app.retrieval.embeddings import EmbeddingIndex


def hybrid_search(
    repository: SqlAlchemyRepository, query: str, limit: int = 15
) -> dict[str, object]:
    with repository.session() as session:
        orders = session.scalars(select(WorkOrderRow)).all()
        incidents = session.scalars(select(IncidentRow)).all()
        insights = session.scalars(select(InsightRow)).all()
        rejected_insights = set(
            session.scalars(
                select(ReviewRow.insight_id).where(ReviewRow.decision == "REJECTED")
            ).all()
        )
    insights = [item for item in insights if item.insight_id not in rejected_insights]
    assets = list_assets(repository)
    active_incident_ids = {item.incident_id for item in insights}
    issue = classify_issue(query)
    year_match = re.search(r"\b(20\d{2})\b", query)
    minimum_match = re.search(r"more than\s+(\d+)", query.lower())
    recurring_only = "recurring" in query.lower()
    structured_query = issue.value != "unknown" or bool(
        year_match or minimum_match or recurring_only
    )
    matching_incidents = (
        _filter_incidents(incidents, issue.value, year_match, minimum_match, recurring_only)
        if structured_query
        else []
    )
    matching_incidents = [
        item for item in matching_incidents if item.incident_id in active_incident_ids
    ]
    semantic = _semantic_orders(orders, query, limit)
    semantic_scores = dict(semantic)
    keyword_terms = set(re.findall(r"[a-z]{3,}", query.lower()))
    scored_orders = [
        (
            order,
            len(
                keyword_terms & set((order.description + " " + order.issue_family).lower().split())
            ),
            semantic_scores.get(order.work_order_id, 0),
        )
        for order in orders
    ]
    ranked_orders = sorted(
        (item for item in scored_orders if item[1] or item[2] > 0),
        key=lambda item: (item[1], item[2], item[0].work_order_id),
        reverse=True,
    )[:limit]
    asset_counts = Counter(item.primary_asset_key for item in matching_incidents)
    insight_map = {item.incident_id: item.payload for item in insights}
    return {
        "query": query,
        "interpreted_filters": {
            "issue_family": None if issue.value == "unknown" else issue.value,
            "year": int(year_match.group()) if year_match else None,
            "minimum_incidents": int(minimum_match.group(1)) if minimum_match else None,
        },
        "summary": f"Found {len(matching_incidents)} matching incidents across {len(asset_counts)} assets.",
        "assets": [
            {
                "asset_key": asset["asset_key"],
                "risk_score": asset["risk_score"],
                "matching_incidents": asset_counts[asset["asset_key"]],
            }
            for asset in assets
            if asset["asset_key"] in asset_counts
        ],
        "incidents": [
            {
                "incident_id": item.incident_id,
                "asset_key": item.primary_asset_key,
                "issue_family": item.issue_family,
                "confidence": item.confidence,
                "supporting_work_orders": insight_map[item.incident_id]["supporting_work_orders"],
            }
            for item in matching_incidents[:limit]
        ],
        "work_orders": [
            {
                "work_order_id": order.work_order_id,
                "date": order.occurred_at.isoformat(),
                "description": order.description,
                "issue_family": order.issue_family,
                "semantic_score": round(semantic_score, 3),
            }
            for order, _, semantic_score in ranked_orders
        ],
    }


def _filter_incidents(incidents, issue, year_match, minimum_match, recurring_only):
    filtered = incidents
    if issue != "unknown":
        filtered = [item for item in filtered if item.issue_family == issue]
    if year_match:
        filtered = [item for item in filtered if item.first_seen.year == int(year_match.group())]
    if minimum_match:
        minimum = int(minimum_match.group(1))
        counts = Counter(item.primary_asset_key for item in filtered)
        filtered = [item for item in filtered if counts[item.primary_asset_key] > minimum]
    if recurring_only:
        filtered = [item for item in filtered if item.recurring]
    return filtered


def _semantic_orders(orders, query: str, limit: int) -> list[tuple[str, float]]:
    if not orders:
        return []
    index = EmbeddingIndex("offline", prefer_transformer=False).fit(
        [order.work_order_id for order in orders],
        [f"{order.description} {order.category} {order.issue_family}" for order in orders],
    )
    return [(neighbor.identifier, neighbor.score) for neighbor in index.query(query, limit)]
