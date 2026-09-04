from datetime import datetime

from pydantic import BaseModel, Field

from app.models.domain import CanonicalComment, CanonicalWorkOrder


class RawWorkOrder(BaseModel):
    work_order_id: str
    occurred_at: datetime
    description: str = ""
    category: str = "unknown"
    department: str = "unknown"
    status: str = "unknown"
    priority: str = "normal"
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RawEntity(BaseModel):
    work_order_id: str
    entity_type: str
    entity_uid: str
    relationship_type: str = "attached"


class RawComment(BaseModel):
    comment_id: str
    work_order_id: str
    created_at: datetime | None = None
    text: str
    source_type: str = "technician"


class ValidationReport(BaseModel):
    source_rows: dict[str, int]
    accepted_rows: dict[str, int]
    rejected_rows: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


class CanonicalDataset(BaseModel):
    work_orders: list[CanonicalWorkOrder]
    comments: list[CanonicalComment]
    entities: list[RawEntity]
    report: ValidationReport
