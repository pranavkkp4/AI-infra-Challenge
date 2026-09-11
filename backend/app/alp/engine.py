from pathlib import Path

import yaml

from app.alp.actions import choose_action
from app.alp.interpretations import choose_interpretation
from app.alp.intervals import infer_pm_interval
from app.alp.observations import build_observations
from app.alp.triggers import direct_cause_sentence
from app.data.feature_engineering import (
    engineer_temporal_features,
    has_repair_signal,
    resolution_signal,
)
from app.incidents.models import IncidentGroup
from app.models.domain import ConfidenceBreakdown, MaintenanceInsight, PossibleCause, SupportLevel


def load_rules(path: Path | None = None) -> dict[str, object]:
    rules_path = path or Path(__file__).with_name("rules.yaml")
    with rules_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def generate_insight(
    incident: IncidentGroup,
    confidence: ConfidenceBreakdown,
    rules: dict[str, object] | None = None,
) -> MaintenanceInsight:
    chosen_rules = rules or load_rules()
    rule = chosen_rules["issues"].get(
        incident.issue_family.value, chosen_rules["issues"]["unknown"]
    )
    evidence_ids = [order.work_order_id for order in incident.work_orders]
    supported_cause = next(
        (
            (sentence, order.work_order_id)
            for order in incident.work_orders
            if (sentence := direct_cause_sentence(order.redacted_notes))
        ),
        None,
    )
    if supported_cause:
        statement, work_order_id = supported_cause
        cause = PossibleCause(
            statement=f"{statement} (WorkOrderId: {work_order_id})",
            support_level=SupportLevel.SUPPORTED,
        )
    elif incident.recurring and incident.issue_family.value != "unknown":
        cause = PossibleCause(
            statement=(
                f"{rule['possible_cause']} (Inference from WorkOrderIds: "
                f"{', '.join(evidence_ids)}.)"
            ),
            support_level=SupportLevel.POSSIBLE,
        )
    else:
        cause = PossibleCause(
            statement="Insufficient evidence to determine cause.",
            support_level=SupportLevel.UNKNOWN,
        )
    label = rule["label"]
    interval = infer_pm_interval(incident)
    cause_evidence_ids = (
        [supported_cause[1]]
        if supported_cause
        else (evidence_ids if cause.support_level != SupportLevel.UNKNOWN else [])
    )
    intervention_ids = [
        order.work_order_id
        for order in incident.work_orders
        if has_repair_signal(" ".join(order.cleaned_notes))
    ]
    interpretation = choose_interpretation(incident, rule)
    interpretation = f"{interpretation} (Evidence: WorkOrderIds: {', '.join(evidence_ids)}.)"
    action = choose_action(incident, rule)
    action = f"{action} (Supporting WorkOrderIds: {', '.join(intervention_ids or evidence_ids)}.)"
    return MaintenanceInsight(
        insight_id=incident.incident_id.replace("INC-", "INS-"),
        incident_id=incident.incident_id,
        title=f"{label} · {incident.primary_asset_key} · {incident.incident_id}",
        asset_key=incident.primary_asset_key,
        issue_family=incident.issue_family,
        summary=(
            f"{len(evidence_ids)} work order(s) form a {incident.issue_family.value.replace('_', ' ')} "
            f"episode from {incident.first_seen:%b %d, %Y} to {incident.last_seen:%b %d, %Y}. "
            f"Evidence: WorkOrderIds: {', '.join(evidence_ids)}."
        ),
        observations=build_observations(incident),
        interpretation=interpretation,
        possible_cause=cause,
        recommended_action=action,
        confidence=confidence.score,
        confidence_level=confidence.level,
        requires_human_review=confidence.requires_human_review,
        supporting_work_orders=evidence_ids,
        contradicting_work_orders=_contradicting_ids(incident),
        confidence_components=confidence,
        pm_interval_recommendation=interval,
        temporal_features=engineer_temporal_features(incident.work_orders),
        evidence_by_field={
            "summary": evidence_ids,
            "observations": evidence_ids,
            "interpretation": evidence_ids,
            "possible_cause": cause_evidence_ids,
            "recommended_action": intervention_ids or evidence_ids,
            "pm_interval_recommendation": interval.supporting_work_orders,
        },
        provenance={
            "alp_contract_version": "alp.v1",
            "alp_library_version": chosen_rules.get("alp", {}).get("version", "unknown"),
            "rule_id": f"issues.{incident.issue_family.value}",
            "expert_note_patterns": sorted(
                {
                    pattern
                    for order in incident.work_orders
                    for pattern in str(order.metadata.get("expert_note_patterns", "")).split(",")
                    if pattern
                }
            ),
            "resolution_status": incident.resolution_status,
            "cause_evidence_work_order_ids": cause_evidence_ids,
            "intervention_evidence_work_order_ids": intervention_ids,
        },
    )


def _contradicting_ids(incident: IncidentGroup) -> list[str]:
    return [
        order.work_order_id
        for order in incident.work_orders
        if any(
            phrase in " ".join(order.cleaned_notes).lower()
            for phrase in ("no issue found", "unable to reproduce", "not maintenance related")
        )
        or _has_unresolved_signal(order)
    ]


def _has_unresolved_signal(order) -> bool:
    return resolution_signal(" ".join(order.cleaned_notes)) == "UNRESOLVED"
