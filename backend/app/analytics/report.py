from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alp.review import apply_review_override
from app.analytics.schemas import PMInsightReport
from app.api.query_service import dashboard_snapshot, list_incidents
from app.models.database import IncidentRow, InsightRow, ReviewRow
from app.models.domain import PMIntervalRecommendation
from app.models.repository import SqlAlchemyRepository


def maintenance_report(repository: SqlAlchemyRepository) -> str:
    dashboard, records = _report_snapshot(repository)
    recurring = [record for record in records if record[0].recurring]
    pending = [record for record in records if record[1].get("review_decision") == "PENDING"]
    additional = [record for record in records if not record[0].recurring]
    sections = [
        "# CivicOps AI Preventive Maintenance Intelligence Report",
        "",
        f"> Dataset: **{dashboard['dataset_label']}**. Findings are decision support, "
        "not completed work authorization.",
        "",
        "## Executive Summary",
        "",
        _summary(dashboard),
        "",
        "## High-Risk Equipment",
        "",
        *_asset_lines(dashboard["high_risk_assets"]),
        "",
        "## Recurring Maintenance Patterns",
        "",
        *_finding_lines(recurring),
        "",
        "## Evidence-Based Findings",
        "",
        "Each finding cites its complete supporting work-order set.",
        "",
        *_finding_lines(additional),
        "",
        "## Preventive Maintenance Recommendations",
        "",
        *_recommendation_lines(_unique_assets(recurring)[:5]),
        "",
        "## Low-Confidence Findings Requiring Review",
        "",
        *_finding_lines(pending),
        "",
        "---",
        "Confidence thresholds require calibration against completed manual audits.",
    ]
    return "\n".join(sections)


def maintenance_report_payload(
    repository: SqlAlchemyRepository, limit: int | None = None, offset: int = 0
) -> dict[str, object]:
    dashboard, records = _report_snapshot(repository)
    if limit is None:
        exported = records[offset:]
        selection_policy = (
            "All active findings ranked by recurrence, issue family, risk, recency, and id."
        )
    else:
        exported = records[offset : offset + limit]
        selection_policy = (
            "Active findings ranked by recurrence, issue family, risk, recency, and id; "
            f"page offset={offset}, limit={limit}."
        )
    payload = {
        "REPORT_TYPE": "PM_INSIGHT_REPORT",
        "SCHEMA_VERSION": "2.0",
        "GENERATED_AT": datetime.now(UTC).isoformat(),
        "DATASET": dashboard["dataset_label"],
        "SUMMARY": dashboard["metrics"],
        "TOTAL_FINDINGS": len(records),
        "EXPORTED_FINDINGS": len(exported),
        "TRUNCATED": len(exported) < len(records),
        "SELECTION_POLICY": selection_policy,
        "FINDINGS": [_structured_finding(incident, insight) for incident, insight in exported],
        "CALIBRATION": _calibration_summary(records),
        "SOURCE_NOTES_POLICY": (
            "Operator output uses cleaned, employee-PII-redacted evidence; external providers "
            "receive location-redacted evidence."
        ),
        "LIMITATIONS": [
            "Risk is a transparent prioritization score, not a failure probability.",
            "PM interval estimates summarize observed recurrence gaps and require local "
            "engineering validation before field authorization.",
        ],
    }
    return PMInsightReport.model_validate(payload).model_dump(mode="json")


def _report_snapshot(
    repository: SqlAlchemyRepository,
) -> tuple[dict[str, object], list[tuple[IncidentRow, dict[str, object]]]]:
    with repository.session() as session:
        dashboard = dashboard_snapshot(session)
        records = _report_records(session)
    active_risks = {item["incident_id"]: item["risk_score"] for item in list_incidents(repository)}
    for incident, insight in records:
        insight["active_risk_score"] = active_risks.get(incident.incident_id, 0)
    records.sort(key=_report_sort_key)
    return dashboard, records


def _report_records(session: Session) -> list[tuple[IncidentRow, dict[str, object]]]:
    rows = session.execute(
        select(IncidentRow, InsightRow, ReviewRow)
        .join(InsightRow, InsightRow.incident_id == IncidentRow.incident_id)
        .outerjoin(ReviewRow, ReviewRow.insight_id == InsightRow.insight_id)
    ).all()
    return [
        (incident, _apply_review(insight.payload, review, incident.recurring))
        for incident, insight, review in rows
        if review is None or review.decision != "REJECTED"
    ]


def _apply_review(
    payload: dict[str, object], review: ReviewRow | None, recurring: bool
) -> dict[str, object]:
    if review is None:
        return payload.copy()
    return apply_review_override(
        payload,
        recurring,
        review.decision,
        review.edited_issue_family,
        review.edited_recommendation,
    )


def _report_sort_key(record: tuple[IncidentRow, dict[str, object]]):
    incident, insight = record
    return (
        not incident.recurring,
        insight["issue_family"] == "unknown",
        -int(insight["active_risk_score"]),
        -incident.last_seen.timestamp(),
        incident.incident_id,
    )


def _summary(dashboard: dict[str, object]) -> str:
    metrics = dashboard["metrics"]
    return (
        f"Analyzed {metrics['total_work_orders']} unique work orders across "
        f"{metrics['unique_assets']} composite asset keys. "
        f"{metrics['recurring_incidents']} recurring incident episodes were detected; "
        f"{metrics['human_review_count']} findings require human review."
    )


def _finding_lines(records) -> list[str]:
    lines: list[str] = []
    for _, insight in records:
        citations = ", ".join(f"`{item}`" for item in insight["supporting_work_orders"])
        lines.extend(
            [
                f"### {insight['title']}",
                f"{insight['summary']} Confidence: **{insight['confidence']:.0%}**.",
                f"Evidence: {citations}.",
                f"Interpretation: {insight['interpretation']}",
                _interval_line(insight),
                f"Review status: {insight.get('review_decision', 'NOT_REQUIRED')}.",
                "",
            ]
        )
    return lines or ["No findings in this section."]


def _recommendation_lines(records) -> list[str]:
    return [
        f"- **{insight['asset_key']}**: {insight['recommended_action']} Evidence: "
        + ", ".join(f"`{item}`" for item in insight["supporting_work_orders"])
        + "."
        for _, insight in records
    ] or ["No recommendations generated."]


def _asset_lines(assets) -> list[str]:
    return [f"- **{asset['asset_key']}**: risk {asset['risk_score']}/100." for asset in assets] or [
        "No equipment records meet the high-risk threshold."
    ]


def _unique_assets(records):
    selected = {}
    for record in records:
        selected.setdefault(record[1]["asset_key"], record)
    return list(selected.values())


def _structured_finding(incident: IncidentRow, insight: dict[str, object]) -> dict[str, object]:
    possible_cause = insight["possible_cause"]
    cause = possible_cause["statement"] if isinstance(possible_cause, dict) else possible_cause
    support = possible_cause.get("support_level") if isinstance(possible_cause, dict) else None
    interval = insight.get("pm_interval_recommendation")
    if not isinstance(interval, dict):
        interval = PMIntervalRecommendation(
            status="INSUFFICIENT_EVIDENCE",
            abstention_reason="No PM interval analysis was persisted.",
        ).model_dump(mode="json")
    return {
        "INSIGHT_ID": insight["insight_id"],
        "INCIDENT_ID": insight["incident_id"],
        "ASSET_KEY": insight["asset_key"],
        "DEPARTMENT": incident.department,
        "ISSUE_FAMILY": insight["issue_family"],
        "EVIDENCE_WINDOW": {
            "first_seen": incident.first_seen.isoformat(),
            "last_seen": incident.last_seen.isoformat(),
        },
        "RECURRING": incident.recurring,
        "RESOLUTION_STATUS": incident.resolution_status,
        "RISK_SCORE": insight.get("active_risk_score", incident.risk_score),
        "OBSERVATIONS": insight["observations"],
        "INTERPRETATION": insight["interpretation"],
        "CAUSAL_FACTOR": cause,
        "CAUSAL_SUPPORT_LEVEL": support,
        "RECOMMENDED_ACTION": insight["recommended_action"],
        "PM_INTERVAL_RECOMMENDATION": interval,
        "CONFIDENCE": {
            "score": insight["confidence"],
            "level": insight["confidence_level"],
            "requires_human_review": insight["requires_human_review"],
            "components": insight["confidence_components"],
        },
        "SUPPORTING_WORK_ORDERS": insight["supporting_work_orders"],
        "CONTRADICTING_WORK_ORDERS": insight["contradicting_work_orders"],
        "EVIDENCE": insight.get("evidence_by_field", {}),
        "PROVENANCE": insight.get("provenance", {}),
        "REVIEW_DECISION": insight.get("review_decision", "NOT_REQUIRED"),
        "HUMAN_OVERRIDE": bool(insight.get("human_override")),
        "DISPATCH_STATUS": "PENDING_HUMAN_AUTHORIZATION",
    }


def _interval_line(insight: dict[str, object]) -> str:
    interval = insight.get("pm_interval_recommendation")
    if not isinstance(interval, dict):
        return "PM interval: **INSUFFICIENT_EVIDENCE**. No PM interval analysis was persisted."
    if interval.get("status") == "RECOMMENDED":
        citations = ", ".join(f"`{item}`" for item in interval["supporting_work_orders"])
        return (
            f"PM interval evidence: **{interval['interval_days']} days** from observed gaps "
            f"({citations})."
        )
    citations = ", ".join(f"`{item}`" for item in interval.get("supporting_work_orders", []))
    evidence = f" Evidence: {citations}." if citations else ""
    return f"PM interval: **INSUFFICIENT_EVIDENCE**. {interval['abstention_reason']}{evidence}"


def _calibration_summary(records) -> dict[str, object]:
    for _, insight in records:
        confidence = insight.get("confidence_components", {})
        calibration = confidence.get("calibration", {}) if isinstance(confidence, dict) else {}
        if calibration.get("applied"):
            return calibration
    return {
        "applied": False,
        "reason": "No explicitly provided calibration artifact was applied.",
    }
