from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.data.pii import redact_pii
from app.models.domain import IssueFamily


class ReviewUpdate(BaseModel):
    decision: Literal["CONFIRMED", "REJECTED", "PENDING"]
    edited_issue_family: IssueFamily | None = None
    edited_recommendation: str | None = Field(default=None, max_length=4000)
    reviewer_note: str | None = Field(default=None, max_length=2000)

    @field_validator("edited_recommendation", "reviewer_note")
    @classmethod
    def redact_user_text(cls, value: str | None) -> str | None:
        return redact_pii(value).text if value else value


class PipelineRequest(BaseModel):
    source: Literal["demo", "raw"] = "demo"
    use_semantic_model: bool = False


class HealthResponse(BaseModel):
    status: str
    database: str
    demo_mode: bool
    dataset_label: str
    analysis_start: datetime | None
    analysis_end: datetime | None
    review_threshold: float
    generated_at: datetime
    llm_provider: str = "deterministic"
    calibration: dict[str, object] = Field(default_factory=dict)
    requires_operator_key: bool = False
