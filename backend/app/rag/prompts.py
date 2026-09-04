from app.incidents.models import IncidentGroup

SYSTEM_INSTRUCTIONS = """You synthesize municipal maintenance evidence.
Use only supplied evidence. Never invent repairs, causes, inspections, or equipment conditions.
Separate observations from inference. If cause evidence is absent, say exactly:
"Insufficient evidence to determine cause."
Every conclusion must cite one or more supplied WorkOrderIds.
Return only the requested structured JSON."""


def build_evidence_prompt(incident: IncidentGroup) -> str:
    blocks = []
    for order in incident.work_orders:
        notes = " | ".join(order.redacted_notes) or "No usable technician note."
        blocks.append(
            f"WORK ORDER: {order.work_order_id}\nDATE: {order.date.isoformat()}\n"
            f"ASSET: {', '.join(order.asset_keys)}\nISSUE FAMILY: {order.issue_family.value}\n"
            f"TECHNICIAN NOTE: {notes}"
        )
    return "\n\n".join(blocks)
