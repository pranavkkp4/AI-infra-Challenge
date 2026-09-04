from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from app.confidence.risk import score_asset_risk_evidence
from app.models.database import (
    AssetRow,
    CommentRow,
    IncidentRow,
    IncidentWorkOrderRow,
    InsightRow,
    PipelineRunRow,
    ReviewRow,
    WorkOrderAssetRow,
    WorkOrderRow,
)
from app.models.repository import SqlAlchemyRepository


def dashboard_payload(repository: SqlAlchemyRepository) -> dict[str, object]:
    with repository.session() as session:
        orders = session.scalars(select(WorkOrderRow)).all()
        assets = session.scalars(select(AssetRow)).all()
        incidents = session.scalars(select(IncidentRow)).all()
        insights = session.scalars(select(InsightRow)).all()
        latest_run = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
        pending = session.scalars(
            select(ReviewRow)
            .join(InsightRow, ReviewRow.insight_id == InsightRow.insight_id)
            .where(ReviewRow.decision == "PENDING")
        ).all()
        rejected_insights = set(
            session.scalars(
                select(ReviewRow.insight_id).where(ReviewRow.decision == "REJECTED")
            ).all()
        )
        incidents = _active_incidents(session, incidents)
        asset_payloads = _active_asset_payloads(session, assets, incidents)
        recurring = [incident for incident in incidents if incident.recurring]
        mean_repeat_days = _mean_repeat_days(session, recurring)
    insights = [item for item in insights if item.insight_id not in rejected_insights]
    average_confidence = sum(item.confidence for item in incidents) / max(1, len(incidents))
    return {
        "dataset_label": dataset_label(latest_run.source if latest_run else None),
        "metrics": {
            "total_work_orders": len(orders),
            "unique_assets": len(assets),
            "recurring_incidents": len(recurring),
            "high_risk_assets": sum(asset["risk_score"] >= 65 for asset in asset_payloads),
            "human_review_count": len(pending),
            "average_confidence": round(average_confidence, 3),
            "repeat_incident_rate": round(len(recurring) / max(1, len(incidents)), 3),
            "issue_resolution_rate": _resolution_rate(incidents),
            "mean_time_between_repeats": mean_repeat_days,
        },
        "incidents_over_time": _incidents_over_time(incidents),
        "issue_distribution": _issue_distribution(incidents),
        "high_risk_assets": _high_risk_assets(asset_payloads),
        "recurrence_trends": _recurrence_trends(incidents),
        "department_activity": _department_activity(orders),
        "patterns": _patterns(recurring, insights),
    }


def list_incidents(repository: SqlAlchemyRepository) -> list[dict[str, object]]:
    with repository.session() as session:
        rows = session.scalars(select(IncidentRow).order_by(IncidentRow.last_seen.desc())).all()
        rows = _active_incidents(session, rows)
        assets = _active_asset_payload_map(session, rows)
    return [_incident_dict(row, assets) for row in rows]


def list_assets(repository: SqlAlchemyRepository) -> list[dict[str, object]]:
    with repository.session() as session:
        assets = session.scalars(select(AssetRow)).all()
        incidents = session.scalars(select(IncidentRow)).all()
        incidents = _active_incidents(session, incidents)
        rows = _active_asset_payloads(session, assets, incidents)
    return sorted(rows, key=lambda row: row["risk_score"], reverse=True)


def incident_detail(repository: SqlAlchemyRepository, incident_id: str) -> dict[str, object] | None:
    with repository.session() as session:
        incident = session.get(IncidentRow, incident_id)
        if not incident:
            return None
        insight = session.scalar(select(InsightRow).where(InsightRow.incident_id == incident_id))
        review = session.scalar(select(ReviewRow).where(ReviewRow.insight_id == insight.insight_id))
        links = session.scalars(
            select(IncidentWorkOrderRow)
            .where(IncidentWorkOrderRow.incident_id == incident_id)
            .order_by(IncidentWorkOrderRow.sequence)
        ).all()
        work_orders = [_work_order_detail(session, link) for link in links]
        active_incidents = _active_incidents(session, session.scalars(select(IncidentRow)).all())
        assets = _active_asset_payload_map(session, active_incidents, {incident.primary_asset_key})
    return {
        "incident": _incident_dict(incident, assets),
        "insight": _reviewed_insight(insight.payload, review),
        "work_orders": work_orders,
    }


def asset_detail(repository: SqlAlchemyRepository, asset_key: str) -> dict[str, object] | None:
    with repository.session() as session:
        asset = session.get(AssetRow, asset_key)
        if not asset:
            return None
        order_ids = session.scalars(
            select(WorkOrderAssetRow.work_order_id).where(WorkOrderAssetRow.asset_key == asset_key)
        ).all()
        orders = session.scalars(
            select(WorkOrderRow)
            .where(WorkOrderRow.work_order_id.in_(order_ids))
            .order_by(WorkOrderRow.occurred_at)
        ).all()
        incident_ids = session.scalars(
            select(IncidentWorkOrderRow.incident_id)
            .where(IncidentWorkOrderRow.work_order_id.in_(order_ids))
            .distinct()
        ).all()
        active_incidents = _active_incidents(session, session.scalars(select(IncidentRow)).all())
        incident_id_set = set(incident_ids)
        incidents = sorted(
            (incident for incident in active_incidents if incident.incident_id in incident_id_set),
            key=lambda incident: incident.first_seen,
        )
        active_incident_ids = [incident.incident_id for incident in incidents]
        insight_rows = session.scalars(
            select(InsightRow).where(InsightRow.incident_id.in_(active_incident_ids))
        ).all()
        reviews = session.scalars(
            select(ReviewRow).where(
                ReviewRow.insight_id.in_([item.insight_id for item in insight_rows])
            )
        ).all()
        relevant_asset_keys = {
            asset_key,
            *(incident.primary_asset_key for incident in incidents),
        }
        asset_payloads = _active_asset_payload_map(session, active_incidents, relevant_asset_keys)
        asset_payload = asset_payloads[asset_key]
    review_by_insight = {row.insight_id: row for row in reviews}
    insight_by_incident = {
        row.incident_id: _reviewed_insight(row.payload, review_by_insight.get(row.insight_id))
        for row in insight_rows
    }
    return {
        "asset": list_assets_for_row(asset_payload, orders, incidents),
        "timeline": [_timeline_order(order, incidents) for order in orders],
        "incidents": [
            {
                **_incident_dict(incident, asset_payloads),
                "insight": insight_by_incident.get(incident.incident_id),
            }
            for incident in incidents
        ],
    }


def review_queue(repository: SqlAlchemyRepository) -> list[dict[str, object]]:
    with repository.session() as session:
        rows = session.execute(
            select(ReviewRow, InsightRow, IncidentRow)
            .join(InsightRow, ReviewRow.insight_id == InsightRow.insight_id)
            .join(IncidentRow, InsightRow.incident_id == IncidentRow.incident_id)
            .order_by(IncidentRow.confidence)
        ).all()
        active_incidents = _active_incidents(session, session.scalars(select(IncidentRow)).all())
        assets = _active_asset_payload_map(session, active_incidents)
    return [
        {
            "review_id": review.review_id,
            "decision": review.decision,
            "reviewer_note": review.reviewer_note,
            "edited_issue_family": review.edited_issue_family,
            "edited_recommendation": review.edited_recommendation,
            "incident": _incident_dict(incident, assets),
            "insight": insight.payload,
        }
        for review, insight, incident in rows
    ]


def _rejected_incident_ids(session) -> set[str]:
    return set(
        session.scalars(
            select(InsightRow.incident_id)
            .join(ReviewRow, ReviewRow.insight_id == InsightRow.insight_id)
            .where(ReviewRow.decision == "REJECTED")
        ).all()
    )


def _active_incidents(session, incidents):
    rejected = _rejected_incident_ids(session)
    return [incident for incident in incidents if incident.incident_id not in rejected]


def _active_asset_payloads(session, assets, incidents) -> list[dict[str, object]]:
    orders_by_incident = _primary_orders_by_incident(session, incidents)
    evidence_by_asset = _risk_evidence_by_asset(incidents, orders_by_incident)
    return [
        _active_asset_payload(asset, evidence_by_asset.get(asset.asset_key, [])) for asset in assets
    ]


def _active_asset_payload_map(session, incidents, asset_keys=None):
    query = select(AssetRow)
    if asset_keys is not None:
        query = query.where(AssetRow.asset_key.in_(asset_keys))
    assets = session.scalars(query).all()
    return {
        payload["asset_key"]: payload
        for payload in _active_asset_payloads(session, assets, incidents)
    }


def _primary_orders_by_incident(session, incidents):
    incident_ids = [incident.incident_id for incident in incidents]
    order_rows = session.execute(
        select(IncidentWorkOrderRow.incident_id, WorkOrderRow)
        .join(WorkOrderRow, IncidentWorkOrderRow.work_order_id == WorkOrderRow.work_order_id)
        .where(IncidentWorkOrderRow.incident_id.in_(incident_ids))
    ).all()
    order_ids = [order.work_order_id for _, order in order_rows]
    asset_links = session.scalars(
        select(WorkOrderAssetRow).where(WorkOrderAssetRow.work_order_id.in_(order_ids))
    ).all()
    assets_by_order: dict[str, list[WorkOrderAssetRow]] = defaultdict(list)
    for link in asset_links:
        assets_by_order[link.work_order_id].append(link)
    orders_by_incident: dict[str, list[tuple[WorkOrderRow, set[str]]]] = defaultdict(list)
    for incident_id, order in order_rows:
        links = assets_by_order[order.work_order_id]
        all_keys = {link.asset_key for link in links}
        primary_keys = {
            link.asset_key
            for link in links
            if link.relationship_type.lower() in {"primary", "asset", "subject"}
        }
        orders_by_incident[incident_id].append((order, primary_keys or all_keys))
    return orders_by_incident


def _risk_evidence_by_asset(incidents, orders_by_incident):
    evidence_by_asset = defaultdict(list)
    for incident in incidents:
        orders_by_asset = defaultdict(list)
        for order, primary_keys in orders_by_incident.get(incident.incident_id, []):
            order_evidence = (order.occurred_at, order.issue_family, order.priority)
            for asset_key in primary_keys:
                orders_by_asset[asset_key].append(order_evidence)
        for asset_key, orders in orders_by_asset.items():
            evidence_by_asset[asset_key].append((incident.resolution_status, orders))
    return evidence_by_asset


def _active_asset_payload(asset, evidence):
    risk = score_asset_risk_evidence(asset.asset_key, evidence)
    return {
        "asset_key": asset.asset_key,
        "entity_type": asset.entity_type,
        "entity_uid": asset.entity_uid,
        "department": asset.department,
        "risk_score": risk.score,
        "risk_reasons": risk.reasons,
    }


def _work_order_detail(session, link: IncidentWorkOrderRow) -> dict[str, object]:
    order = session.get(WorkOrderRow, link.work_order_id)
    comments = session.scalars(
        select(CommentRow).where(CommentRow.work_order_id == link.work_order_id)
    ).all()
    assets = session.scalars(
        select(WorkOrderAssetRow.asset_key).where(
            WorkOrderAssetRow.work_order_id == link.work_order_id
        )
    ).all()
    return {
        "work_order_id": order.work_order_id,
        "date": order.occurred_at.isoformat(),
        "category": order.category,
        "department": order.department,
        "status": order.status,
        "priority": order.priority,
        "issue_family": order.issue_family,
        "asset_keys": assets,
        "comments": [
            {
                "redacted_text": comment.redacted_text,
                "was_redacted": comment.was_redacted,
                "is_meaningful": comment.is_meaningful,
                "source_type": comment.source_type,
            }
            for comment in comments
        ],
        "match_explanation": link.match_explanation,
    }


def dataset_label(source: str | None) -> str:
    return (
        "Synthetic Demo Dataset"
        if source and Path(source).name.lower() == "demo"
        else "Operational Dataset"
    )


def _reviewed_insight(payload: dict[str, object], review: ReviewRow | None) -> dict[str, object]:
    result = payload.copy()
    if review:
        result["review_decision"] = review.decision
        if review.edited_issue_family:
            result["issue_family"] = review.edited_issue_family
        if review.edited_recommendation:
            result["recommended_action"] = review.edited_recommendation
    return result


def _incident_dict(
    row: IncidentRow, assets: dict[str, dict[str, object]] | None = None
) -> dict[str, object]:
    risk_score = (
        assets.get(row.primary_asset_key, {}).get("risk_score", 0)
        if assets is not None
        else row.risk_score
    )
    return {
        "incident_id": row.incident_id,
        "asset_key": row.primary_asset_key,
        "issue_family": row.issue_family,
        "department": row.department,
        "first_seen": row.first_seen.isoformat(),
        "last_seen": row.last_seen.isoformat(),
        "work_order_count": row.work_order_count,
        "recurring": row.recurring,
        "resolution_status": row.resolution_status,
        "confidence": round(row.confidence, 3),
        "confidence_level": row.confidence_level,
        "requires_human_review": row.requires_human_review,
        "risk_score": risk_score,
    }


def list_assets_for_row(asset, orders, incidents) -> dict[str, object]:
    return {
        **asset,
        "total_work_orders": len(orders),
        "recurring_issues": sum(incident.recurring for incident in incidents),
        "last_service_date": max(order.occurred_at for order in orders).isoformat()
        if orders
        else None,
    }


def _timeline_order(order, incidents) -> dict[str, object]:
    incident = next(
        (
            item
            for item in incidents
            if item.issue_family == order.issue_family
            and item.first_seen <= order.occurred_at <= item.last_seen
        ),
        None,
    )
    return {
        "work_order_id": order.work_order_id,
        "date": order.occurred_at.isoformat(),
        "category": order.category,
        "issue_family": order.issue_family,
        "status": order.status,
        "priority": order.priority,
        "incident_id": incident.incident_id if incident else None,
        "is_repeat": bool(incident and incident.recurring),
    }


def _resolution_rate(incidents) -> float | None:
    measurable = [item for item in incidents if item.resolution_status != "UNKNOWN"]
    if not measurable:
        return None
    return round(
        sum(item.resolution_status == "RESOLVED" for item in measurable) / len(measurable), 3
    )


def _mean_repeat_days(session, incidents) -> float | None:
    if not incidents:
        return None
    incident_ids = [item.incident_id for item in incidents]
    rows = session.execute(
        select(IncidentWorkOrderRow.incident_id, WorkOrderRow.occurred_at)
        .join(WorkOrderRow, IncidentWorkOrderRow.work_order_id == WorkOrderRow.work_order_id)
        .where(IncidentWorkOrderRow.incident_id.in_(incident_ids))
        .order_by(IncidentWorkOrderRow.incident_id, WorkOrderRow.occurred_at)
    ).all()
    by_incident: dict[str, list] = defaultdict(list)
    for incident_id, occurred_at in rows:
        by_incident[incident_id].append(occurred_at)
    gaps = [
        (dates[index] - dates[index - 1]).days
        for dates in by_incident.values()
        for index in range(1, len(dates))
    ]
    return round(sum(gaps) / len(gaps), 1) if gaps else None


def _incidents_over_time(incidents) -> list[dict[str, object]]:
    counts = Counter(item.first_seen.strftime("%Y-%m") for item in incidents)
    return [{"period": period, "incidents": count} for period, count in sorted(counts.items())]


def _issue_distribution(incidents) -> list[dict[str, object]]:
    counts = Counter(item.issue_family for item in incidents)
    return [{"name": name, "value": value} for name, value in counts.most_common()]


def _high_risk_assets(assets) -> list[dict[str, object]]:
    ranked = sorted(assets, key=lambda item: item["risk_score"], reverse=True)[:8]
    return [{"asset_key": item["asset_key"], "risk_score": item["risk_score"]} for item in ranked]


def _recurrence_trends(incidents) -> list[dict[str, object]]:
    by_year: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "recurring": 0})
    for incident in incidents:
        year = str(incident.first_seen.year)
        by_year[year]["total"] += 1
        by_year[year]["recurring"] += int(incident.recurring)
    return [{"year": year, **values} for year, values in sorted(by_year.items())]


def _department_activity(orders) -> list[dict[str, object]]:
    counts = Counter(item.department for item in orders)
    return [{"department": name, "work_orders": count} for name, count in counts.most_common()]


def _patterns(recurring, insights) -> list[dict[str, object]]:
    insight_by_incident = {item.incident_id: item.payload for item in insights}
    by_issue: dict[str, list[IncidentRow]] = defaultdict(list)
    for incident in recurring:
        by_issue[incident.issue_family].append(incident)
    patterns = []
    for issue, rows in sorted(by_issue.items(), key=lambda item: len(item[1]), reverse=True)[:4]:
        supporting = [
            work_order
            for row in rows
            if row.incident_id in insight_by_incident
            for work_order in insight_by_incident[row.incident_id]["supporting_work_orders"]
        ]
        active_rows = [row for row in rows if row.incident_id in insight_by_incident]
        if not active_rows:
            continue
        patterns.append(
            {
                "title": f"Repeated {issue.replace('_', ' ')} detected across {len(set(row.primary_asset_key for row in active_rows))} assets.",
                "incident_count": len(active_rows),
                "supporting_work_orders": supporting[:6],
            }
        )
    return patterns
