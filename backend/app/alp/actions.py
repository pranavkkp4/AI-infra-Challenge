from app.incidents.models import IncidentGroup


def choose_action(incident: IncidentGroup, rule: dict[str, str]) -> str:
    if not incident.recurring:
        return "Monitor for recurrence and verify the recorded disposition before preventive work is authorized."
    return rule["action"]
