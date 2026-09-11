from statistics import median

from app.incidents.models import IncidentGroup
from app.models.domain import PMIntervalRecommendation


def infer_pm_interval(incident: IncidentGroup) -> PMIntervalRecommendation:
    """Estimate a PM cadence from observed episode gaps without inventing a schedule."""

    all_ids = [order.work_order_id for order in incident.work_orders]
    if not incident.recurring:
        return PMIntervalRecommendation(
            status="INSUFFICIENT_EVIDENCE",
            supporting_work_orders=all_ids,
            abstention_reason="The episode is not classified as recurring; no PM cadence is inferred.",
        )
    issue_orders = [
        order for order in incident.work_orders if order.issue_family == incident.issue_family
    ]
    if len(issue_orders) < 3:
        return PMIntervalRecommendation(
            status="INSUFFICIENT_EVIDENCE",
            supporting_work_orders=all_ids,
            abstention_reason=(
                f"At least three work orders classified as {incident.issue_family.value} "
                "are required to infer a PM interval."
            ),
        )

    issue_orders.sort(key=lambda order: order.date)
    gaps = [
        round(
            (issue_orders[index].date - issue_orders[index - 1].date).total_seconds() / 86_400,
            3,
        )
        for index in range(1, len(issue_orders))
    ]
    positive_gaps = [gap for gap in gaps if gap > 0]
    if len(positive_gaps) < 2:
        return PMIntervalRecommendation(
            status="INSUFFICIENT_EVIDENCE",
            observed_gap_days=gaps,
            supporting_work_orders=[order.work_order_id for order in issue_orders],
            abstention_reason=(
                "At least two positive recurrence gaps are required; the available episode "
                "dates do not provide enough time-separated evidence."
            ),
        )

    return PMIntervalRecommendation(
        status="RECOMMENDED",
        interval_days=round(float(median(positive_gaps)), 1),
        observed_gap_days=gaps,
        supporting_work_orders=[order.work_order_id for order in issue_orders],
    )


def infer_pm_interval_recommendation(incident: IncidentGroup) -> PMIntervalRecommendation:
    """Named alias for callers that prefer the full contract name."""

    return infer_pm_interval(incident)
