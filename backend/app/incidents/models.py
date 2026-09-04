from datetime import datetime

from pydantic import BaseModel

from app.models.domain import CandidateMatch, CanonicalWorkOrder, IssueFamily


class IncidentGroup(BaseModel):
    incident_id: str
    primary_asset_key: str
    issue_family: IssueFamily
    department: str
    first_seen: datetime
    last_seen: datetime
    work_orders: list[CanonicalWorkOrder]
    matches: list[CandidateMatch]
    recurring: bool
    resolution_status: str
