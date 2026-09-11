import re

from app.models.domain import MaintenanceInsight


class GroundingError(ValueError):
    pass


CLAIM_FIELDS = (
    "summary",
    "observations",
    "interpretation",
    "possible_cause",
    "recommended_action",
    "pm_interval_recommendation",
)
WORK_ORDER_CITATION_PATTERN = re.compile(r"\bWorkOrderIds?\s*:\s*([^\n.;)]*)", re.IGNORECASE)


def enforce_grounding(insight: MaintenanceInsight, retrieved_work_order_ids: set[str]) -> None:
    cited = set(insight.supporting_work_orders) | set(insight.contradicting_work_orders)
    interval = getattr(insight, "pm_interval_recommendation", None)
    if interval is not None:
        cited.update(interval.supporting_work_orders)
    unsupported = cited - retrieved_work_order_ids
    if unsupported:
        raise GroundingError(
            "Insight cited work orders outside retrieved evidence: "
            + ", ".join(sorted(unsupported))
        )
    evidence_by_field = getattr(insight, "evidence_by_field", {}) or {}
    unknown_fields = set(evidence_by_field) - set(CLAIM_FIELDS)
    if unknown_fields:
        raise GroundingError(
            "Insight contains unsupported evidence fields: " + ", ".join(sorted(unknown_fields))
        )
    for field in CLAIM_FIELDS:
        field_ids = set(evidence_by_field.get(field, []))
        unsupported_field_ids = field_ids - retrieved_work_order_ids
        if unsupported_field_ids:
            raise GroundingError(
                f"Evidence mapping for {field} cited work orders outside retrieved evidence: "
                + ", ".join(sorted(unsupported_field_ids))
            )
        if not field_ids <= cited:
            raise GroundingError(
                f"Evidence mapping for {field} must be included in supporting or contradicting citations"
            )
        text = _claim_text(insight, field)
        referenced_ids = _referenced_work_order_ids(text, cited)
        unmapped_ids = referenced_ids - field_ids
        if unmapped_ids:
            raise GroundingError(
                f"Claim field {field} referenced unmapped work orders: "
                + ", ".join(sorted(unmapped_ids))
            )
        if _requires_explicit_citation(insight, field) and not referenced_ids:
            raise GroundingError(f"Claim field {field} requires an explicit WorkOrderId citation")


def _claim_text(insight: MaintenanceInsight, field: str) -> str:
    if field == "observations":
        return " ".join(insight.observations)
    if field == "possible_cause":
        return insight.possible_cause.statement
    if field == "pm_interval_recommendation":
        return ""
    value = getattr(insight, field, "")
    return str(value)


def _requires_explicit_citation(insight: MaintenanceInsight, field: str) -> bool:
    if field == "possible_cause" and insight.possible_cause.support_level.value == "UNKNOWN":
        return False
    return field != "pm_interval_recommendation"


def _referenced_work_order_ids(text: str, candidate_ids: set[str]) -> set[str]:
    return {
        candidate
        for citation in WORK_ORDER_CITATION_PATTERN.findall(text)
        for candidate in candidate_ids
        if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", citation)
    }
