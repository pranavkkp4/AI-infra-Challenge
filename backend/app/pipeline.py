from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alp.engine import generate_insight, load_rules
from app.confidence.engine import score_confidence
from app.confidence.risk import score_asset_risk
from app.data.normalizer import normalize_source
from app.data.validators import build_asset_key
from app.incidents.grouping import group_incidents
from app.models.database import (
    AssetRow,
    Base,
    CommentRow,
    IncidentRow,
    IncidentWorkOrderRow,
    InsightRow,
    PipelineRunRow,
    ReviewRow,
    WorkOrderAssetRow,
    WorkOrderRow,
)
from app.models.repository import DATABASE_WRITE_LOCK, SqlAlchemyRepository
from app.rag.grounding import enforce_grounding
from app.retrieval.candidates import generate_candidates


def run_pipeline(
    source_dir: Path,
    repository: SqlAlchemyRepository,
    embedding_model: str,
    review_threshold: float,
    prefer_transformer: bool = False,
) -> dict[str, object]:
    started_at = datetime.now(UTC).replace(tzinfo=None)
    dataset = normalize_source(source_dir)
    rules = load_rules()
    matches, index = generate_candidates(
        dataset.work_orders,
        embedding_model,
        weights=rules["grouping"]["weights"],
        prefer_transformer=prefer_transformer,
    )
    incidents = group_incidents(
        dataset.work_orders,
        matches,
        threshold=rules["grouping"]["threshold"],
        episode_max_span_days=rules["grouping"]["episode_max_span_days"],
    )
    confidences = {
        incident.incident_id: score_confidence(
            incident, review_threshold, rules["confidence"]["weights"]
        )
        for incident in incidents
    }
    insights = {
        incident.incident_id: generate_insight(incident, confidences[incident.incident_id], rules)
        for incident in incidents
    }
    for incident in incidents:
        enforce_grounding(
            insights[incident.incident_id],
            {order.work_order_id for order in incident.work_orders},
        )
    asset_keys = sorted({asset for order in dataset.work_orders for asset in order.asset_keys})
    risks = {asset: score_asset_risk(asset, incidents) for asset in asset_keys}
    with DATABASE_WRITE_LOCK:
        _persist(
            repository, dataset, incidents, confidences, insights, risks, started_at, source_dir
        )
    return {
        "work_orders": len(dataset.work_orders),
        "assets": len(asset_keys),
        "incidents": len(incidents),
        "recurring_incidents": sum(incident.recurring for incident in incidents),
        "review_queue": sum(
            confidence.requires_human_review for confidence in confidences.values()
        ),
        "embedding_backend": index.backend,
        "validation": dataset.report.model_dump(),
    }


def _persist(
    repository, dataset, incidents, confidences, insights, risks, started_at, source_dir
) -> None:
    repository.create_schema()
    existing_reviews = _load_existing_reviews(repository)
    existing_runs = _load_pipeline_runs(repository)
    with repository.engine.begin() as connection:
        # Drop this table explicitly so legacy insight FKs do not block schema migration.
        ReviewRow.__table__.drop(connection, checkfirst=True)
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)
        session = Session(connection, expire_on_commit=False)
        try:
            session.add_all(PipelineRunRow(**values) for values in existing_runs)
            _write_work_orders(session, dataset.work_orders)
            _write_assets(session, dataset.work_orders, risks)
            session.flush()
            _write_source_evidence(session, dataset)
            session.flush()
            _write_incidents(session, incidents, confidences, risks)
            session.flush()
            _write_insights(session, incidents, insights)
            session.flush()
            _write_reviews(session, incidents, confidences, insights, existing_reviews)
            session.add(_pipeline_run(dataset, started_at, source_dir))
            session.flush()
        finally:
            session.close()


def _write_work_orders(session, work_orders) -> None:
    session.add_all(
        WorkOrderRow(
            work_order_id=order.work_order_id,
            occurred_at=order.date,
            category=order.category,
            department=order.department,
            description=order.description,
            status=order.status,
            priority=order.priority,
            issue_family=order.issue_family.value,
            metadata_json=order.metadata,
        )
        for order in work_orders
    )


def _write_assets(session, work_orders, risks) -> None:
    departments: dict[str, list[str]] = {}
    for order in work_orders:
        for asset in order.asset_keys:
            departments.setdefault(asset, []).append(order.department)
    for asset, risk in risks.items():
        entity_type, entity_uid = asset.split(":", 1)
        session.add(
            AssetRow(
                asset_key=asset,
                entity_type=entity_type,
                entity_uid=entity_uid,
                department=Counter(departments[asset]).most_common(1)[0][0],
                risk_score=risk.score,
                risk_reasons=risk.reasons,
            )
        )


def _write_source_evidence(session, dataset) -> None:
    session.add_all(
        WorkOrderAssetRow(
            work_order_id=entity.work_order_id,
            asset_key=build_asset_key(entity.entity_type, entity.entity_uid),
            relationship_type=entity.relationship_type,
        )
        for entity in dataset.entities
    )
    session.add_all(CommentRow(**comment.model_dump()) for comment in dataset.comments)


def _write_incidents(session, incidents, confidences, risks) -> None:
    for incident in incidents:
        confidence = confidences[incident.incident_id]
        session.add(
            IncidentRow(
                incident_id=incident.incident_id,
                primary_asset_key=incident.primary_asset_key,
                issue_family=incident.issue_family.value,
                department=incident.department,
                first_seen=incident.first_seen,
                last_seen=incident.last_seen,
                work_order_count=len(incident.work_orders),
                recurring=incident.recurring,
                resolution_status=incident.resolution_status,
                confidence=confidence.score,
                confidence_level=confidence.level.value,
                requires_human_review=confidence.requires_human_review,
                risk_score=risks[incident.primary_asset_key].score,
            )
        )


def _write_insights(session, incidents, insights) -> None:
    for incident in incidents:
        for sequence, order in enumerate(incident.work_orders):
            session.add(
                IncidentWorkOrderRow(
                    incident_id=incident.incident_id,
                    work_order_id=order.work_order_id,
                    sequence=sequence,
                    match_explanation=_best_explanation(order.work_order_id, incident.matches),
                )
            )
        insight = insights[incident.incident_id]
        session.add(
            InsightRow(
                insight_id=insight.insight_id,
                incident_id=incident.incident_id,
                payload=insight.model_dump(mode="json"),
            )
        )


def _write_reviews(session, incidents, confidences, insights, existing_reviews) -> None:
    active_insight_ids: set[str] = set()
    for incident in incidents:
        confidence = confidences[incident.incident_id]
        insight = insights[incident.incident_id]
        active_insight_ids.add(insight.insight_id)
        previous = existing_reviews.get(insight.insight_id)
        if previous or confidence.requires_human_review:
            session.add(
                ReviewRow(
                    review_id=previous["review_id"]
                    if previous
                    else f"REV-{uuid4().hex[:10].upper()}",
                    insight_id=insight.insight_id,
                    decision=previous["decision"] if previous else "PENDING",
                    edited_issue_family=previous["edited_issue_family"] if previous else None,
                    edited_recommendation=previous["edited_recommendation"] if previous else None,
                    reviewer_note=previous["reviewer_note"] if previous else None,
                    reviewed_at=previous["reviewed_at"] if previous else None,
                )
            )
    for insight_id, previous in existing_reviews.items():
        if insight_id not in active_insight_ids:
            session.add(ReviewRow(insight_id=insight_id, **previous))


def _pipeline_run(dataset, started_at, source_dir) -> PipelineRunRow:
    return PipelineRunRow(
        run_id=f"RUN-{uuid4().hex[:10].upper()}",
        source=str(source_dir),
        status="COMPLETED",
        validation_counts={
            "accepted": sum(dataset.report.accepted_rows.values()),
            "rejected": sum(dataset.report.rejected_rows.values()),
        },
        started_at=started_at,
        completed_at=datetime.now(UTC).replace(tzinfo=None),
    )


def _load_existing_reviews(repository: SqlAlchemyRepository) -> dict[str, dict[str, object]]:
    with repository.session() as session:
        rows = session.scalars(select(ReviewRow)).all()
    return {
        row.insight_id: {
            "review_id": row.review_id,
            "decision": row.decision,
            "edited_issue_family": row.edited_issue_family,
            "edited_recommendation": row.edited_recommendation,
            "reviewer_note": row.reviewer_note,
            "reviewed_at": row.reviewed_at,
        }
        for row in rows
    }


def _load_pipeline_runs(repository: SqlAlchemyRepository) -> list[dict[str, object]]:
    with repository.session() as session:
        rows = session.scalars(select(PipelineRunRow)).all()
    return [
        {column.name: getattr(row, column.name) for column in PipelineRunRow.__table__.columns}
        for row in rows
    ]


def _best_explanation(work_order_id: str, matches) -> dict[str, object]:
    relevant = [
        match
        for match in matches
        if work_order_id in {match.source_work_order_id, match.target_work_order_id}
    ]
    if not relevant:
        return {"type": "episode_anchor", "reasons": ["first or only evidence record"]}
    best = max(relevant, key=lambda match: match.weighted_score)
    return best.model_dump(mode="json")
