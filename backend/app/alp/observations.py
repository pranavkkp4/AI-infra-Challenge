from app.incidents.models import IncidentGroup


def build_observations(incident: IncidentGroup) -> list[str]:
    ids = ", ".join(order.work_order_id for order in incident.work_orders)
    span = (incident.last_seen - incident.first_seen).days
    observations = [
        f"{len(incident.work_orders)} work order(s) are linked to {incident.primary_asset_key} across {span} days ({ids})."
    ]
    if incident.recurring:
        observations.append(
            f"The {incident.issue_family.value.replace('_', ' ')} issue appears in multiple work orders."
        )
    repair_count = sum(
        any(
            word in " ".join(order.cleaned_notes).lower()
            for word in ("replaced", "repaired", "patched", "cleared", "reset")
        )
        for order in incident.work_orders
    )
    if repair_count:
        observations.append(
            f"Technician evidence records {repair_count} maintenance intervention(s)."
        )
    observations.append(
        f"Latest directly measurable resolution signal: {incident.resolution_status}."
    )
    return observations
