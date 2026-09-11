from functools import lru_cache

from app.alp.engine import load_rules


def apply_review_override(
    payload: dict[str, object],
    recurring: bool,
    decision: str | None = None,
    edited_issue_family: str | None = None,
    edited_recommendation: str | None = None,
) -> dict[str, object]:
    result = payload.copy()
    if decision:
        result["review_decision"] = decision
    if edited_issue_family:
        _apply_family(result, edited_issue_family, recurring)
    if edited_recommendation:
        result["recommended_action"] = edited_recommendation
        result["human_override"] = True
    return result


def _apply_family(result: dict[str, object], family: str, recurring: bool) -> None:
    rule = _issue_rules().get(family, _issue_rules()["unknown"])
    label = rule["label"]
    result.update(
        {
            "title": f"{label} · {result['asset_key']} · {result['incident_id']}",
            "issue_family": family,
            "summary": (
                f"Human review assigned this evidence set to the {family.replace('_', ' ')} "
                "issue family."
            ),
            "observations": [
                item
                for item in result["observations"]
                if " issue appears in at least " not in str(item)
            ],
            "interpretation": rule["interpretation"]
            if recurring
            else (
                "The records form one related episode, but fewer than three work orders are "
                "available; recurrence cannot yet be established."
            ),
            "possible_cause": {
                "statement": "Insufficient evidence to determine cause.",
                "support_level": "UNKNOWN",
            },
            "recommended_action": rule["action"],
            "human_override": True,
        }
    )


@lru_cache(maxsize=1)
def _issue_rules() -> dict[str, dict[str, str]]:
    rules = load_rules()["issues"]
    return {str(family): dict(values) for family, values in rules.items()}
