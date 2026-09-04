from app.incidents.models import IncidentGroup


def choose_interpretation(incident: IncidentGroup, rule: dict[str, str]) -> str:
    if len(incident.work_orders) == 1:
        return "A single maintenance record was detected; recurrence cannot yet be established."
    return rule["interpretation"]
