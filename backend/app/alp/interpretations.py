from app.incidents.models import IncidentGroup


def choose_interpretation(incident: IncidentGroup, rule: dict[str, str]) -> str:
    if not incident.recurring:
        return (
            "The records form one related episode, but fewer than three work orders are "
            "available; recurrence cannot yet be established."
        )
    return rule["interpretation"]
