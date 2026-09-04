from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


class IssueFamily(StrEnum):
    WATER_LEAK = "water_leak"
    MAIN_BREAK = "main_break"
    LOW_PRESSURE = "low_pressure"
    SEWER_BACKUP = "sewer_backup"
    POTHOLE = "pothole"
    PAVEMENT_DAMAGE = "pavement_damage"
    METER_FAILURE = "meter_failure"
    HVAC_FAILURE = "hvac_failure"
    ELECTRICAL_ISSUE = "electrical_issue"
    UNKNOWN = "unknown"


class SupportLevel(StrEnum):
    SUPPORTED = "SUPPORTED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


Score = Annotated[float, Field(ge=0, le=1)]


class CanonicalComment(BaseModel):
    comment_id: str
    work_order_id: str
    created_at: datetime | None = None
    raw_text: str
    clean_text: str
    redacted_text: str
    was_redacted: bool
    is_meaningful: bool
    source_type: str = "technician"


class CanonicalWorkOrder(BaseModel):
    work_order_id: str
    asset_keys: list[str]
    primary_asset_keys: list[str] = Field(default_factory=list)
    date: datetime
    category: str
    department: str
    description: str = ""
    cleaned_notes: list[str] = Field(default_factory=list)
    redacted_notes: list[str] = Field(default_factory=list)
    status: str = "unknown"
    priority: str = "normal"
    issue_family: IssueFamily = IssueFamily.UNKNOWN
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CandidateMatch(BaseModel):
    source_work_order_id: str
    target_work_order_id: str
    semantic_similarity: Score
    same_asset: bool
    related_asset: bool = False
    days_apart: int = Field(ge=0)
    temporal_score: Score
    same_issue_family: bool
    weighted_score: Score
    reasons: list[str]


class ConfidenceBreakdown(BaseModel):
    semantic_consistency: Score
    asset_consistency: Score
    temporal_consistency: Score
    evidence_strength: Score
    issue_agreement: Score
    conflict_penalty: Score = 0
    score: Score
    level: ConfidenceLevel
    requires_human_review: bool


class PossibleCause(BaseModel):
    statement: str
    support_level: SupportLevel


class MaintenanceInsight(BaseModel):
    insight_id: str
    incident_id: str
    title: str
    asset_key: str
    issue_family: IssueFamily
    summary: str
    observations: list[str]
    interpretation: str
    possible_cause: PossibleCause
    recommended_action: str
    confidence: Score
    confidence_level: ConfidenceLevel
    requires_human_review: bool
    supporting_work_orders: list[str]
    contradicting_work_orders: list[str] = Field(default_factory=list)
    confidence_components: ConfidenceBreakdown
    generated_by: str = "deterministic_alp"

    @model_validator(mode="after")
    def require_supporting_evidence(self) -> "MaintenanceInsight":
        if not self.supporting_work_orders:
            raise ValueError("Every maintenance insight requires supporting WorkOrderIds")
        return self


class AssetRisk(BaseModel):
    asset_key: str
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    components: dict[str, float]


class TemporalFeatures(BaseModel):
    days_since_previous: int | None
    incidents_30d: int
    incidents_90d: int
    incidents_365d: int
    recurrence_interval_days: float | None
    previous_repair_attempts: int
    issue_persistence: Score
