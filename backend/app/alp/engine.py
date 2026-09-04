from pathlib import Path

import yaml

from app.alp.actions import choose_action
from app.alp.interpretations import choose_interpretation
from app.alp.observations import build_observations
from app.alp.triggers import direct_cause_sentence
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
    all_notes = [note for order in incident.work_orders for note in order.redacted_notes]
    supported_cause = direct_cause_sentence(all_notes)
    if supported_cause:
        cause = PossibleCause(statement=supported_cause, support_level=SupportLevel.SUPPORTED)
    elif incident.recurring and incident.issue_family.value != "unknown":
        cause = PossibleCause(statement=rule["possible_cause"], support_level=SupportLevel.POSSIBLE)
    else:
        cause = PossibleCause(
            statement="Insufficient evidence to determine cause.",
            support_level=SupportLevel.UNKNOWN,
        )
    label = rule["label"]
    return MaintenanceInsight(
        insight_id=incident.incident_id.replace("INC-", "INS-"),
        incident_id=incident.incident_id,
        title=f"{label} · {incident.primary_asset_key}",
        asset_key=incident.primary_asset_key,
        issue_family=incident.issue_family,
        summary=(
            f"{len(evidence_ids)} work order(s) form a {incident.issue_family.value.replace('_', ' ')} "
            f"episode from {incident.first_seen:%b %d, %Y} to {incident.last_seen:%b %d, %Y}."
        ),
        observations=build_observations(incident),
        interpretation=choose_interpretation(incident, rule),
        possible_cause=cause,
        recommended_action=choose_action(incident, rule),
        confidence=confidence.score,
        confidence_level=confidence.level,
        requires_human_review=confidence.requires_human_review,
        supporting_work_orders=evidence_ids,
        contradicting_work_orders=_contradicting_ids(incident),
        confidence_components=confidence,
    )


def _contradicting_ids(incident: IncidentGroup) -> list[str]:
    return [
        order.work_order_id
        for order in incident.work_orders
        if any(
            phrase in " ".join(order.cleaned_notes).lower()
            for phrase in ("no issue found", "unable to reproduce", "not maintenance related")
        )
    ]
