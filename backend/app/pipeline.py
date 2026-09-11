import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alp.engine import generate_insight, load_rules
from app.alp.intervals import infer_pm_interval
from app.confidence.engine import score_confidence
from app.confidence.risk import score_asset_risks
from app.config import Settings, get_settings
from app.data.feature_engineering import engineer_temporal_features
from app.data.normalizer import normalize_source
from app.data.validators import build_asset_key, classify_asset
from app.evaluation.calibration import (
    CalibrationArtifact,
    default_demo_calibration_path,
    load_calibration_artifact,
)
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
from app.rag.prompts import SYSTEM_INSTRUCTIONS, build_evidence_prompt
from app.rag.providers import DeterministicProvider, LLMProvider, create_provider
from app.retrieval.candidates import generate_candidates


def run_pipeline(
    source_dir: Path,
    repository: SqlAlchemyRepository,
    embedding_model: str,
    review_threshold: float,
    prefer_transformer: bool = False,
    provider: LLMProvider | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    selected_settings = settings or get_settings()
    started_at = datetime.now(UTC).replace(tzinfo=None)
    calibration = _load_configured_calibration(selected_settings, source_dir)
    dataset = normalize_source(source_dir, prefer_semantic_triggers=prefer_transformer)
    rules = load_rules()
    analysis_orders = [
        order for order in dataset.work_orders if order.metadata.get("analysis_eligible")
    ]
    matches, index = generate_candidates(
        analysis_orders,
        embedding_model,
        weights=rules["grouping"]["weights"],
        prefer_transformer=prefer_transformer,
    )
    incidents = group_incidents(
        analysis_orders,
        matches,
        threshold=rules["grouping"]["threshold"],
        episode_max_span_days=rules["grouping"]["episode_max_span_days"],
    )
    confidences = {
        incident.incident_id: score_confidence(
            incident,
            review_threshold,
            rules["confidence"]["weights"],
            calibration_artifact=calibration,
        )
        for incident in incidents
    }
    configured_provider = provider
    if configured_provider is None and selected_settings.llm_provider.lower() != "deterministic":
        configured_provider = create_provider(selected_settings)
    insights = {}
    for incident in incidents:
        confidence = confidences[incident.incident_id]

        def fallback(current_incident=incident, current_confidence=confidence):
            return generate_insight(current_incident, current_confidence, rules)

        selected_provider = configured_provider
        if selected_provider is None or (
            isinstance(selected_provider, DeterministicProvider)
            and selected_provider.fallback is None
        ):
            selected_provider = create_provider(selected_settings, deterministic_fallback=fallback)
        evidence_prompt = build_evidence_prompt(incident)
        insight = _run_provider(selected_provider, SYSTEM_INSTRUCTIONS, evidence_prompt)
        insight = _complete_insight(
            insight,
            incident,
            confidence,
            calibration,
            index.backend,
            len(matches),
        )
        enforce_grounding(
            insight,
            {order.work_order_id for order in incident.work_orders},
        )
        insights[incident.incident_id] = insight
    asset_keys = sorted({asset for order in dataset.work_orders for asset in order.asset_keys})
    risks = score_asset_risks(asset_keys, incidents)
    with DATABASE_WRITE_LOCK:
        _persist(
            repository, dataset, incidents, confidences, insights, risks, started_at, source_dir
        )
    return {
        "work_orders": len(dataset.work_orders),
        "assets": len(asset_keys),
        "analysis_eligible_work_orders": len(analysis_orders),
        "incidents": len(incidents),
        "recurring_incidents": sum(incident.recurring for incident in incidents),
        "review_queue": sum(
            confidence.requires_human_review for confidence in confidences.values()
        ),
        "embedding_backend": index.backend,
        "provider": configured_provider.provider_name
        if configured_provider is not None
        else selected_settings.llm_provider.lower(),
        "calibration": calibration.provenance()
        if calibration
        else {"applied": False, "reason": "No calibration artifact configured"},
        "validation": dataset.report.model_dump(),
    }


def _load_configured_calibration(
    settings: Settings, source_dir: Path
) -> CalibrationArtifact | None:
    path = settings.calibration_artifact_path
    bundled_demo = Path(__file__).resolve().parents[2] / "data" / "demo"
    is_bundled_demo = source_dir.resolve() == bundled_demo.resolve()
    if path is None and settings.demo_mode and is_bundled_demo:
        path = default_demo_calibration_path()
    if path is None:
        if settings.calibration_enabled:
            raise ValueError("Calibration is enabled but no artifact path is configured")
        return None
    if not path.exists():
        if is_bundled_demo:
            raise ValueError(f"Bundled demo calibration artifact is missing: {path}")
        if settings.calibration_enabled:
            raise ValueError(f"Calibration artifact was not found: {path}")
        return None
    return load_calibration_artifact(path)


def _run_provider(provider: LLMProvider, system: str, evidence: str):
    coroutine = provider.synthesize(system, evidence)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


def _complete_insight(
    insight,
    incident,
    confidence,
    calibration,
    retrieval_backend: str,
    candidate_count: int,
):
    if insight.incident_id != incident.incident_id:
        raise ValueError("Provider insight incident_id does not match retrieved incident")
    if insight.asset_key != incident.primary_asset_key:
        raise ValueError("Provider insight asset_key does not match retrieved incident")
    evidence_ids = [order.work_order_id for order in incident.work_orders]
    interval = infer_pm_interval(incident)
    cause_evidence = evidence_ids if insight.possible_cause.support_level.value != "UNKNOWN" else []
    field_evidence = {
        "summary": evidence_ids,
        "observations": evidence_ids,
        "interpretation": evidence_ids,
        "possible_cause": cause_evidence,
        "recommended_action": evidence_ids,
        "pm_interval_recommendation": interval.supporting_work_orders,
    }
    for field, cited_ids in insight.evidence_by_field.items():
        safe_ids = [work_order_id for work_order_id in cited_ids if work_order_id in evidence_ids]
        if safe_ids:
            field_evidence[field] = safe_ids
    provenance = {
        **insight.provenance,
        "retrieval_backend": retrieval_backend,
        "candidate_count": candidate_count,
        "calibration": confidence.calibration,
        "calibration_artifact_configured": calibration is not None,
    }
    completed = insight.model_copy(
        update={
            "confidence": confidence.score,
            "confidence_level": confidence.level,
            "requires_human_review": confidence.requires_human_review,
            "confidence_components": confidence,
            "pm_interval_recommendation": interval,
            "temporal_features": engineer_temporal_features(incident.work_orders),
            "evidence_by_field": field_evidence,
            "provenance": provenance,
        }
    )
    return type(insight).model_validate(completed)


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
                asset_class=classify_asset(entity_type),
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
        if previous and previous["edited_issue_family"]:
            session.get(IncidentRow, incident.incident_id).issue_family = previous[
                "edited_issue_family"
            ]
        if (previous and previous["decision"] != "PENDING") or confidence.requires_human_review:
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
        source=_source_identity(dataset, source_dir),
        status="COMPLETED",
        validation_counts={
            "accepted": sum(dataset.report.accepted_rows.values()),
            "rejected": sum(dataset.report.rejected_rows.values()),
        },
        started_at=started_at,
        completed_at=datetime.now(UTC).replace(tzinfo=None),
    )


def _source_identity(dataset, source_dir) -> str:
    source_rows = dataset.report.source_rows
    if source_rows == {
        "WORKORDER.csv": 37_778,
        "WOENTITY.csv": 867_448,
        "WOCOMMENT.csv": 33_572,
    }:
        return f"starter:{source_dir}"
    if any(order.metadata.get("source") == "cityworks_csv" for order in dataset.work_orders):
        return f"cityworks:{source_dir}"
    bundled_demo = Path(__file__).resolve().parents[2] / "data" / "demo"
    if source_dir.resolve() == bundled_demo.resolve():
        return f"demo:{source_dir}"
    return str(source_dir)


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
