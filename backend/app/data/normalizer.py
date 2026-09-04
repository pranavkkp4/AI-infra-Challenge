import re
from pathlib import Path

import polars as pl

from app.data.cleaner import clean_comment, deduplicate_boilerplate
from app.data.feature_engineering import classify_issue
from app.data.loader import load_source_frames, resolve_column
from app.data.pii import redact_pii
from app.data.schemas import CanonicalDataset, RawEntity, ValidationReport
from app.data.validators import build_asset_key, parse_timestamp, valid_identifier
from app.models.domain import CanonicalComment, CanonicalWorkOrder


def normalize_source(source_dir: Path) -> CanonicalDataset:
    frames = load_source_frames(source_dir)
    work_orders, rejected_orders = _normalize_work_orders(frames["WORKORDER.csv"])
    entities, rejected_entities = _normalize_entities(frames["WOENTITY.csv"])
    comments, rejected_comments = _normalize_comments(frames["WOCOMMENT.csv"])
    known_order_ids = set(work_orders)
    valid_entities = [item for item in entities if item.work_order_id in known_order_ids]
    valid_comments = [item for item in comments if item.work_order_id in known_order_ids]
    rejected_entities += len(entities) - len(valid_entities)
    rejected_comments += len(comments) - len(valid_comments)
    by_work_order: dict[str, list[RawEntity]] = {}
    for entity in valid_entities:
        by_work_order.setdefault(entity.work_order_id, []).append(entity)
    comments_by_order: dict[str, list[CanonicalComment]] = {}
    for comment in valid_comments:
        comments_by_order.setdefault(comment.work_order_id, []).append(comment)
    canonical: list[CanonicalWorkOrder] = []
    for record in work_orders.values():
        order_entities = by_work_order.get(record["work_order_id"], [])
        asset_keys = sorted(
            {build_asset_key(entity.entity_type, entity.entity_uid) for entity in order_entities}
        )
        if not asset_keys:
            rejected_orders += 1
            continue
        order_comments = comments_by_order.get(record["work_order_id"], [])
        notes = [comment.clean_text for comment in order_comments if comment.is_meaningful]
        redacted = [comment.redacted_text for comment in order_comments if comment.is_meaningful]
        primary_asset_keys = (
            sorted(
                {
                    build_asset_key(entity.entity_type, entity.entity_uid)
                    for entity in order_entities
                    if entity.relationship_type.lower() in {"primary", "asset", "subject"}
                }
            )
            or asset_keys
        )
        classification_text = " ".join([record["description"], *notes])
        canonical.append(
            CanonicalWorkOrder(
                **record,
                asset_keys=asset_keys,
                primary_asset_keys=primary_asset_keys,
                cleaned_notes=notes,
                redacted_notes=redacted,
                issue_family=classify_issue(classification_text),
            )
        )
    accepted_order_ids = {order.work_order_id for order in canonical}
    entities = [item for item in valid_entities if item.work_order_id in accepted_order_ids]
    comments = [item for item in valid_comments if item.work_order_id in accepted_order_ids]
    rejected_entities += len(valid_entities) - len(entities)
    rejected_comments += len(valid_comments) - len(comments)
    report = ValidationReport(
        source_rows={name: frame.height for name, frame in frames.items()},
        accepted_rows={
            "work_orders": len(canonical),
            "entities": len(entities),
            "comments": len(comments),
        },
        rejected_rows={
            "work_orders": rejected_orders,
            "entities": rejected_entities,
            "comments": rejected_comments,
        },
        warnings=["Descriptions were used for classification only, not as technician evidence."],
    )
    return CanonicalDataset(
        work_orders=sorted(canonical, key=lambda order: (order.date, order.work_order_id)),
        comments=comments,
        entities=entities,
        report=report,
    )


def _normalize_work_orders(frame: pl.DataFrame) -> tuple[dict[str, dict[str, object]], int]:
    columns = {
        "id": resolve_column(frame, ("WorkOrderId", "work_order_id", "WOID")),
        "date": resolve_column(frame, ("CreatedDate", "OccurredAt", "Date", "OpenDate")),
        "description": resolve_column(frame, ("Description", "Summary", "Title"), False),
        "category": resolve_column(frame, ("Category", "WorkType", "Type"), False),
        "department": resolve_column(frame, ("Department", "Division", "Agency"), False),
        "status": resolve_column(frame, ("Status", "WorkOrderStatus"), False),
        "priority": resolve_column(frame, ("Priority", "Severity"), False),
    }
    records: dict[str, dict[str, object]] = {}
    rejected = 0
    for row in frame.iter_rows(named=True):
        identifier = row.get(columns["id"])
        occurred_at = parse_timestamp(row.get(columns["date"]))
        if not valid_identifier(identifier) or occurred_at is None:
            rejected += 1
            continue
        work_order_id = str(identifier).strip()
        if work_order_id in records:
            rejected += 1
            continue
        records[work_order_id] = {
            "work_order_id": work_order_id,
            "date": occurred_at,
            "description": _value(row, columns["description"]),
            "category": _value(row, columns["category"], "unknown"),
            "department": _value(row, columns["department"], "unknown"),
            "status": _value(row, columns["status"], "unknown"),
            "priority": _value(row, columns["priority"], "normal"),
            "metadata": {"source": "csv"},
        }
    return records, rejected


def _normalize_entities(frame: pl.DataFrame) -> tuple[list[RawEntity], int]:
    work_order = resolve_column(frame, ("WorkOrderId", "work_order_id", "WOID"))
    entity_type = resolve_column(frame, ("EntityType", "entity_type", "AssetType"))
    entity_uid = resolve_column(frame, ("EntityUid", "entity_uid", "AssetId"))
    relationship = resolve_column(frame, ("RelationshipType", "Relation", "Role"), False)
    entities: dict[tuple[str, str], RawEntity] = {}
    rejected = 0
    for row in frame.iter_rows(named=True):
        values = (row.get(work_order), row.get(entity_type), row.get(entity_uid))
        if not all(valid_identifier(value) for value in values):
            rejected += 1
            continue
        try:
            asset_key = build_asset_key(values[1], values[2])
        except ValueError:
            rejected += 1
            continue
        key = (str(values[0]).strip(), asset_key)
        if key in entities:
            rejected += 1
            continue
        entities[key] = RawEntity(
            work_order_id=key[0],
            entity_type=str(values[1]).strip(),
            entity_uid=str(values[2]).strip(),
            relationship_type=_value(row, relationship, "attached"),
        )
    return list(entities.values()), rejected


def _normalize_comments(frame: pl.DataFrame) -> tuple[list[CanonicalComment], int]:
    columns = {
        "id": resolve_column(frame, ("CommentId", "comment_id", "Id"), False),
        "work_order": resolve_column(frame, ("WorkOrderId", "work_order_id", "WOID")),
        "date": resolve_column(frame, ("CreatedDate", "CommentDate", "Date"), False),
        "text": resolve_column(frame, ("Comment", "CommentText", "Text", "Notes")),
        "type": resolve_column(frame, ("CommentType", "SourceType", "Type"), False),
    }
    raw_texts = [_value(row, columns["text"]) for row in frame.iter_rows(named=True)]
    repeated = deduplicate_boilerplate(raw_texts)
    comments: dict[str, CanonicalComment] = {}
    rejected = 0
    for index, row in enumerate(frame.iter_rows(named=True), start=1):
        work_order_id = row.get(columns["work_order"])
        raw_text = _value(row, columns["text"])
        normalized = re.sub(r"\W+", " ", raw_text.lower()).strip()
        if not valid_identifier(work_order_id) or not raw_text:
            rejected += 1
            continue
        clean_text = "" if normalized in repeated else clean_comment(raw_text)
        redaction = redact_pii(clean_text)
        identifier = row.get(columns["id"]) if columns["id"] else None
        comment_id = str(identifier).strip() if valid_identifier(identifier) else f"COMMENT-{index}"
        if comment_id in comments:
            rejected += 1
            continue
        comments[comment_id] = CanonicalComment(
            comment_id=comment_id,
            work_order_id=str(work_order_id).strip(),
            created_at=parse_timestamp(row.get(columns["date"])) if columns["date"] else None,
            raw_text=raw_text,
            clean_text=clean_text,
            redacted_text=redaction.text,
            was_redacted=redaction.was_redacted,
            is_meaningful=bool(clean_text),
            source_type=_value(row, columns["type"], "technician"),
        )
    return list(comments.values()), rejected


def _value(row: dict[str, object], column: str | None, default: str = "") -> str:
    if not column or row.get(column) is None:
        return default
    return str(row[column]).strip() or default
