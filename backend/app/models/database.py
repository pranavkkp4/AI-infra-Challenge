from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorkOrderRow(Base):
    __tablename__ = "work_orders"
    work_order_id: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    category: Mapped[str] = mapped_column(String)
    department: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String)
    priority: Mapped[str] = mapped_column(String)
    issue_family: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class AssetRow(Base):
    __tablename__ = "assets"
    asset_key: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=False)
    entity_type: Mapped[str] = mapped_column(String)
    entity_uid: Mapped[str] = mapped_column(String)
    department: Mapped[str] = mapped_column(String)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)


class WorkOrderAssetRow(Base):
    __tablename__ = "work_order_assets"
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("work_orders.work_order_id"), primary_key=True, autoincrement=False
    )
    asset_key: Mapped[str] = mapped_column(
        ForeignKey("assets.asset_key"), primary_key=True, autoincrement=False
    )
    relationship_type: Mapped[str] = mapped_column(String, default="attached")


class CommentRow(Base):
    __tablename__ = "comments"
    comment_id: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=False)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.work_order_id"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    clean_text: Mapped[str] = mapped_column(Text)
    redacted_text: Mapped[str] = mapped_column(Text)
    was_redacted: Mapped[bool] = mapped_column(Boolean)
    is_meaningful: Mapped[bool] = mapped_column(Boolean)
    source_type: Mapped[str] = mapped_column(String)


class IncidentRow(Base):
    __tablename__ = "incidents"
    incident_id: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=False)
    primary_asset_key: Mapped[str] = mapped_column(String)
    issue_family: Mapped[str] = mapped_column(String)
    department: Mapped[str] = mapped_column(String)
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime)
    work_order_count: Mapped[int] = mapped_column(Integer)
    recurring: Mapped[bool] = mapped_column(Boolean)
    resolution_status: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    confidence_level: Mapped[str] = mapped_column(String)
    requires_human_review: Mapped[bool] = mapped_column(Boolean)
    risk_score: Mapped[int] = mapped_column(Integer)


class IncidentWorkOrderRow(Base):
    __tablename__ = "incident_work_orders"
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.incident_id"), primary_key=True, autoincrement=False
    )
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("work_orders.work_order_id"), primary_key=True, autoincrement=False
    )
    sequence: Mapped[int] = mapped_column(Integer)
    match_explanation: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class InsightRow(Base):
    __tablename__ = "insights"
    insight_id: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=False)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id"), unique=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class ReviewRow(Base):
    __tablename__ = "reviews"
    review_id: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=False)
    insight_id: Mapped[str] = mapped_column(String, unique=True)
    decision: Mapped[str] = mapped_column(String, default="PENDING")
    edited_issue_family: Mapped[str | None] = mapped_column(String, nullable=True)
    edited_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PipelineRunRow(Base):
    __tablename__ = "pipeline_runs"
    run_id: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=False)
    source: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    validation_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
