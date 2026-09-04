from app.models.domain import MaintenanceInsight


class GroundingError(ValueError):
    pass


def enforce_grounding(insight: MaintenanceInsight, retrieved_work_order_ids: set[str]) -> None:
    cited = set(insight.supporting_work_orders) | set(insight.contradicting_work_orders)
    unsupported = cited - retrieved_work_order_ids
    if unsupported:
        raise GroundingError(
            "Insight cited work orders outside retrieved evidence: "
            + ", ".join(sorted(unsupported))
        )
