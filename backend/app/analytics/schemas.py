from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.domain import PMIntervalRecommendation, SupportLevel


class PMInsightFinding(BaseModel):
    INSIGHT_ID: str
    INCIDENT_ID: str
    ASSET_KEY: str
    DEPARTMENT: str
    ISSUE_FAMILY: str
    EVIDENCE_WINDOW: dict[str, str]
    RECURRING: bool
    RESOLUTION_STATUS: str
    RISK_SCORE: int = Field(ge=0, le=100)
    OBSERVATIONS: list[str]
    INTERPRETATION: str
    CAUSAL_FACTOR: str
    CAUSAL_SUPPORT_LEVEL: SupportLevel | None
    RECOMMENDED_ACTION: str
    PM_INTERVAL_RECOMMENDATION: PMIntervalRecommendation
    CONFIDENCE: dict[str, Any]
    SUPPORTING_WORK_ORDERS: list[str] = Field(min_length=1)
    CONTRADICTING_WORK_ORDERS: list[str] = Field(default_factory=list)
    EVIDENCE: dict[str, list[str]] = Field(default_factory=dict)
    PROVENANCE: dict[str, Any] = Field(default_factory=dict)
    REVIEW_DECISION: str
    HUMAN_OVERRIDE: bool
    DISPATCH_STATUS: str

    @model_validator(mode="after")
    def validate_citations(self) -> "PMInsightFinding":
        cited = set(self.SUPPORTING_WORK_ORDERS) | set(self.CONTRADICTING_WORK_ORDERS)
        interval_ids = set(self.PM_INTERVAL_RECOMMENDATION.supporting_work_orders)
        if not interval_ids <= cited:
            raise ValueError("PM interval evidence must cite work orders in the finding")
        if any(not set(ids) <= cited for ids in self.EVIDENCE.values()):
            raise ValueError("Field-level evidence must cite work orders in the finding")
        return self


class PMInsightReport(BaseModel):
    REPORT_TYPE: Literal["PM_INSIGHT_REPORT"]
    SCHEMA_VERSION: str
    GENERATED_AT: str
    DATASET: str
    SUMMARY: dict[str, Any]
    TOTAL_FINDINGS: int = Field(ge=0)
    EXPORTED_FINDINGS: int = Field(ge=0)
    TRUNCATED: bool
    SELECTION_POLICY: str
    FINDINGS: list[PMInsightFinding]
    CALIBRATION: dict[str, Any]
    SOURCE_NOTES_POLICY: str
    LIMITATIONS: list[str]

    @model_validator(mode="after")
    def validate_completeness(self) -> "PMInsightReport":
        if len(self.FINDINGS) != self.EXPORTED_FINDINGS:
            raise ValueError("EXPORTED_FINDINGS must equal the number of FINDINGS")
        if (self.EXPORTED_FINDINGS < self.TOTAL_FINDINGS) != self.TRUNCATED:
            raise ValueError("TRUNCATED must describe the exported finding count")
        return self
