from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReviewUpdate(BaseModel):
    decision: Literal["CONFIRMED", "REJECTED", "PENDING"]
    edited_issue_family: str | None = None
    edited_recommendation: str | None = None
    reviewer_note: str | None = Field(default=None, max_length=2000)


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
