from app.api.query_service import (
    dashboard_payload,
    incident_detail,
    list_assets,
    list_incidents,
    review_queue,
)
from app.models.repository import SqlAlchemyRepository


def maintenance_report(repository: SqlAlchemyRepository) -> str:
    dashboard = dashboard_payload(repository)
    incidents = list_incidents(repository)
    high_risk = [item for item in list_assets(repository) if item["risk_score"] >= 65][:8]
    recurring = [item for item in incidents if item["recurring"]][:10]
    pending_ids = {
        item["incident"]["incident_id"]
        for item in review_queue(repository)
        if item["decision"] == "PENDING"
    }
    review = [item for item in incidents if item["incident_id"] in pending_ids][:10]
    sections = [
        "# CivicOps AI Preventive Maintenance Intelligence Report",
        "",
        f"> Dataset: **{dashboard['dataset_label']}**. Findings are decision support, "
        "not completed work authorization.",
        "",
        "## Executive Summary",
        "",
        f"Analyzed {dashboard['metrics']['total_work_orders']} unique work orders across "
        f"{dashboard['metrics']['unique_assets']} composite asset keys. "
        f"{dashboard['metrics']['recurring_incidents']} recurring incident episodes were detected; "
        f"{dashboard['metrics']['human_review_count']} findings require human review.",
        "",
        "## High-Risk Assets",
        "",
        *_asset_lines(high_risk),
        "",
        "## Recurring Maintenance Patterns",
        "",
        *_finding_lines(repository, recurring),
        "",
        "## Evidence-Based Findings",
        "",
        "Each finding below is generated from technician evidence and cites its complete supporting work-order set.",
        "",
        *_finding_lines(repository, recurring[:5]),
        "",
        "## Preventive Maintenance Recommendations",
        "",
        *_recommendation_lines(repository, _unique_asset_incidents(recurring)[:5]),
        "",
        "## Low-Confidence Findings Requiring Review",
        "",
        *_finding_lines(repository, review),
        "",
        "---",
        "Confidence thresholds are demo defaults and must be calibrated against completed manual audits.",
    ]
    return "\n".join(sections)


def _finding_lines(repository, incidents) -> list[str]:
    lines: list[str] = []
    for incident in incidents:
        detail = incident_detail(repository, incident["incident_id"])
        if detail is None:
            continue
        insight = detail["insight"]
        if insight.get("review_decision") == "REJECTED":
            continue
        citations = ", ".join(f"`{item}`" for item in insight["supporting_work_orders"])
        lines.extend(
            [
                f"### {insight['title']}",
                f"{insight['summary']} Confidence: **{insight['confidence']:.0%}**.",
                f"Evidence: {citations}.",
                f"Interpretation: {insight['interpretation']}",
                "",
            ]
        )
    return lines or ["No findings in this section."]


def _recommendation_lines(repository, incidents) -> list[str]:
    lines: list[str] = []
    for incident in incidents:
        detail = incident_detail(repository, incident["incident_id"])
        if detail is None:
            continue
        insight = detail["insight"]
        if insight.get("review_decision") == "REJECTED":
            continue
        citations = ", ".join(f"`{item}`" for item in insight["supporting_work_orders"])
        lines.append(
            f"- **{insight['asset_key']}**: {insight['recommended_action']} Evidence: {citations}."
        )
    return lines or ["No recommendations generated."]


def _asset_lines(assets) -> list[str]:
    return [
        f"- **{asset['asset_key']}**: risk {asset['risk_score']}/100. "
        + "; ".join(asset["risk_reasons"])
        for asset in assets
    ] or ["No assets meet the high-risk threshold."]


def _unique_asset_incidents(incidents) -> list[dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    for incident in sorted(incidents, key=lambda item: item["risk_score"], reverse=True):
        selected.setdefault(incident["asset_key"], incident)
    return list(selected.values())
