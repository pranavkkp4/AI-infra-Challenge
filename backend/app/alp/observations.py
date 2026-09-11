from app.data.feature_engineering import has_repair_signal
from app.incidents.models import IncidentGroup


def build_observations(incident: IncidentGroup) -> list[str]:
    ids = ", ".join(order.work_order_id for order in incident.work_orders)
    span = (incident.last_seen - incident.first_seen).days
    observations = [
        f"{len(incident.work_orders)} work order(s) are linked to {incident.primary_asset_key} "
        f"across {span} days (WorkOrderIds: {ids})."
    ]
    if incident.recurring:
        issue_ids = [
            order.work_order_id
            for order in incident.work_orders
            if order.issue_family == incident.issue_family
        ]
        observations.append(
            f"The {incident.issue_family.value.replace('_', ' ')} issue appears in at least "
            f"three linked work orders (WorkOrderIds: {', '.join(issue_ids)})."
        )
        gaps = [
            round(
                (
                    incident.work_orders[index].date - incident.work_orders[index - 1].date
                ).total_seconds()
                / 86_400,
                3,
            )
            for index in range(1, len(incident.work_orders))
        ]
        observations.append(
            f"Observed recurrence gaps are {', '.join(f'{gap:g}' for gap in gaps)} days "
            f"(WorkOrderIds: {ids})."
        )
    intervention_ids = [
        order.work_order_id
        for order in incident.work_orders
        if has_repair_signal(" ".join(order.cleaned_notes))
    ]
    if intervention_ids:
        observations.append(
            f"Technician evidence records {len(intervention_ids)} maintenance intervention(s) "
            f"(WorkOrderIds: {', '.join(intervention_ids)})."
        )
    latest_id = incident.work_orders[-1].work_order_id
    observations.append(
        f"Latest directly measurable resolution signal: {incident.resolution_status} "
        f"(WorkOrderId: {latest_id})."
    )
    return observations
