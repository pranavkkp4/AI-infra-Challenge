from app.incidents.models import IncidentGroup


def choose_action(incident: IncidentGroup, rule: dict[str, str]) -> str:
    if len(incident.work_orders) == 1:
        return "Monitor for recurrence and verify the recorded disposition before preventive work is authorized."
    return rule["action"]
