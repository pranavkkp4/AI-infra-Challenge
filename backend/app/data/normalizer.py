import re
from collections import Counter
from pathlib import Path

import polars as pl

from app.data.cleaner import clean_comment, deduplicate_boilerplate, is_maintenance_comment
from app.data.feature_engineering import (
    classify_issue_with_evidence,
    detect_expert_note_patterns,
    propagate_sequence_context,
)
from app.data.loader import load_source_frames, resolve_column
from app.data.pii import redact_pii
from app.data.schemas import CanonicalDataset, RawEntity, ValidationReport
from app.data.validators import (
    FALLBACK_RELATIONSHIP_TYPES,
    PRIMARY_RELATIONSHIP_TYPES,
    build_asset_key,
    classify_asset,
    parse_timestamp,
    valid_identifier,
)
from app.models.domain import CanonicalComment, CanonicalWorkOrder

MAX_ANALYSIS_ASSETS_PER_ORDER = 10
CATCH_ALL_MIN_WORK_ORDERS = 500
KNOWN_CATCH_ALL_ASSETS = {
    "CITYFACILITIES:0",
    "CITYFACILITIES:642",
    "CITY_DEPTS:LEGAL",
    "CITY_DEPTS:MIS",
}


def normalize_source(
    source_dir: Path,
    max_assets_per_order: int = MAX_ANALYSIS_ASSETS_PER_ORDER,
    catch_all_min_work_orders: int = CATCH_ALL_MIN_WORK_ORDERS,
    prefer_semantic_triggers: bool = False,
) -> CanonicalDataset:
    frames = load_source_frames(source_dir)
    work_orders, rejected_orders = _normalize_work_orders(frames["WORKORDER.csv"])
    entities, rejected_entities, exclusions = _normalize_entities(
        frames["WOENTITY.csv"], max_assets_per_order, catch_all_min_work_orders
    )
    comments, rejected_comments = _normalize_comments(frames["WOCOMMENT.csv"])
    known_order_ids = set(work_orders)
    entities, unknown_entities = _with_known_orders(entities, known_order_ids)
    comments, unknown_comments = _with_known_orders(comments, known_order_ids)
    canonical, missing_assets = _assemble_work_orders(
        work_orders, entities, comments, prefer_semantic_triggers
    )
    canonical = propagate_sequence_context(canonical)
    exclusions["non_maintenance_work_orders"] = sum(
        order.metadata.get("analysis_exclusion") == "administrative or non-maintenance note"
        for order in canonical
    )
    accepted_order_ids = {order.work_order_id for order in canonical}
    entities, dropped_entities = _with_known_orders(entities, accepted_order_ids)
    comments, dropped_comments = _with_known_orders(comments, accepted_order_ids)
    report = ValidationReport(
        source_rows={name: frame.height for name, frame in frames.items()},
        accepted_rows={
            "work_orders": len(canonical),
            "entities": len(entities),
            "comments": len(comments),
        },
        rejected_rows={
            "work_orders": rejected_orders + missing_assets,
            "entities": rejected_entities + unknown_entities + dropped_entities,
            "comments": rejected_comments + unknown_comments + dropped_comments,
        },
        excluded_rows=exclusions,
        warnings=[
            "Descriptions are metadata only; classifications and retrieval use redacted notes.",
            "Bulk inventory links and high-degree catch-all assets are excluded before analysis.",
            "Administrative and explicit non-maintenance notes are retained but excluded from analysis.",
        ],
    )
    return CanonicalDataset(
        work_orders=sorted(canonical, key=lambda order: (order.date, order.work_order_id)),
        comments=comments,
        entities=entities,
        report=report,
    )


def _with_known_orders(items, known_order_ids: set[str]):
    accepted = [item for item in items if item.work_order_id in known_order_ids]
    return accepted, len(items) - len(accepted)


def _assemble_work_orders(work_orders, entities, comments, prefer_semantic_triggers):
    entities_by_order = _group_by_order(entities)
    comments_by_order = _group_by_order(comments)
    canonical: list[CanonicalWorkOrder] = []
    rejected = 0
    for record in work_orders.values():
        order_entities = entities_by_order.get(record["work_order_id"], [])
        if not order_entities:
            rejected += 1
            continue
        canonical.append(
            _canonical_order(
                record,
                order_entities,
                comments_by_order.get(record["work_order_id"], []),
                prefer_semantic_triggers,
            )
        )
    return canonical, rejected


def _group_by_order(items):
    grouped = {}
    for item in items:
        grouped.setdefault(item.work_order_id, []).append(item)
    return grouped


def _canonical_order(
    record, entities, comments, prefer_semantic_triggers=False
) -> CanonicalWorkOrder:
    asset_keys = sorted(
        {build_asset_key(entity.entity_type, entity.entity_uid) for entity in entities}
    )
    primary_keys = _preferred_asset_keys(entities, PRIMARY_RELATIONSHIP_TYPES)
    if not primary_keys:
        primary_keys = _preferred_asset_keys(entities, FALLBACK_RELATIONSHIP_TYPES)
    meaningful = [comment for comment in comments if comment.is_meaningful]
    clean_notes = [comment.clean_text for comment in meaningful]
    redacted_notes = [comment.redacted_text for comment in meaningful]
    issue_match = classify_issue_with_evidence(" ".join(redacted_notes), prefer_semantic_triggers)
    metadata = dict(record["metadata"])
    metadata["issue_match_method"] = issue_match.method
    metadata["issue_trigger"] = issue_match.trigger
    metadata["issue_trigger_score"] = round(issue_match.score, 4)
    metadata["expert_note_patterns"] = ",".join(
        detect_expert_note_patterns(" ".join(redacted_notes))
    )
    maintenance_text = " ".join(redacted_notes)
    is_maintenance = is_maintenance_comment(maintenance_text)
    metadata["analysis_eligible"] = bool(primary_keys and redacted_notes and is_maintenance)
    if metadata["analysis_eligible"]:
        metadata["analysis_exclusion"] = ""
    elif redacted_notes and not is_maintenance:
        metadata["analysis_exclusion"] = "administrative or non-maintenance note"
    else:
        metadata["analysis_exclusion"] = "no meaningful note or analysis asset"
    return CanonicalWorkOrder(
        **{**record, "metadata": metadata},
        asset_keys=asset_keys,
        primary_asset_keys=primary_keys,
        cleaned_notes=clean_notes,
        redacted_notes=redacted_notes,
        issue_family=issue_match.family,
    )


def _preferred_asset_keys(entities, relationship_types: set[str]) -> list[str]:
    candidates = [
        entity for entity in entities if entity.relationship_type.lower() in relationship_types
    ]
    equipment = [
        entity for entity in candidates if classify_asset(entity.entity_type) == "equipment"
    ]
    selected = equipment or candidates
    return sorted({build_asset_key(entity.entity_type, entity.entity_uid) for entity in selected})


def _normalize_work_orders(frame: pl.DataFrame) -> tuple[dict[str, dict[str, object]], int]:
    columns = _work_order_columns(frame)
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
        records[work_order_id] = _work_order_record(row, columns, work_order_id, occurred_at)
    return records, rejected


def _work_order_columns(frame: pl.DataFrame) -> dict[str, str | None]:
    return {
        "id": resolve_column(frame, ("WorkOrderId", "work_order_id", "WOID")),
        "date": resolve_column(
            frame, ("InitiateDate", "CreatedDate", "OccurredAt", "Date", "OpenDate")
        ),
        "description": resolve_column(frame, ("Description", "Summary", "Title"), False),
        "category": resolve_column(frame, ("AssetGroup", "Category", "WorkType", "Type"), False),
        "department": resolve_column(frame, ("Shop", "Department", "Division", "Agency"), False),
        "status": resolve_column(frame, ("Status", "WorkOrderStatus"), False),
        "priority": resolve_column(frame, ("Priority", "Severity"), False),
        "address": resolve_column(frame, ("WOAddress", "Address"), False),
        "location": resolve_column(frame, ("Location",), False),
        "reactive": resolve_column(frame, ("IsReactive",), False),
        "text10": resolve_column(frame, ("Text10",), False),
        "apply_to": resolve_column(frame, ("ApplyToEntity",), False),
    }


def _work_order_record(row, columns, work_order_id, occurred_at) -> dict[str, object]:
    return {
        "work_order_id": work_order_id,
        "date": occurred_at,
        "description": _value(row, columns["description"]),
        "category": _normalized_label(_value(row, columns["category"], "unknown")),
        "department": _normalized_label(
            _value(row, columns["department"], "unknown"), uppercase=True
        ),
        "status": _value(row, columns["status"], "unknown").upper(),
        "priority": _value(row, columns["priority"], "normal"),
        "metadata": {
            "source": "cityworks_csv"
            if _normalized_name(columns["date"]) == "initiatedate"
            else "csv",
            "site": _value(row, columns["address"]) or _value(row, columns["location"]),
            "location": _value(row, columns["location"]),
            "is_reactive": _as_bool(row.get(columns["reactive"])) if columns["reactive"] else None,
            "text10": _value(row, columns["text10"]),
            "apply_to_entity": _value(row, columns["apply_to"]),
        },
    }


def _normalize_entities(
    frame: pl.DataFrame, max_assets_per_order: int, catch_all_min_work_orders: int
) -> tuple[list[RawEntity], int, dict[str, int]]:
    columns = _entity_columns(frame)
    bulk_orders = _bulk_order_ids(frame, columns, max_assets_per_order)
    candidates, rejected, bulk_links = _entity_candidates(frame, columns, bulk_orders)
    asset_counts = Counter(
        build_asset_key(entity.entity_type, entity.entity_uid) for entity in candidates.values()
    )
    catch_alls = KNOWN_CATCH_ALL_ASSETS | {
        asset for asset, count in asset_counts.items() if count >= catch_all_min_work_orders
    }
    entities = [
        entity
        for entity in candidates.values()
        if build_asset_key(entity.entity_type, entity.entity_uid) not in catch_alls
    ]
    return (
        entities,
        rejected,
        {
            "bulk_work_orders": len(bulk_orders),
            "bulk_entity_links": bulk_links,
            "catch_all_entity_links": len(candidates) - len(entities),
            "catch_all_assets": len(catch_alls & set(asset_counts)),
        },
    )


def _entity_columns(frame: pl.DataFrame) -> dict[str, str | None]:
    return {
        "work_order": resolve_column(frame, ("WorkOrderId", "work_order_id", "WOID")),
        "entity_type": resolve_column(frame, ("EntityType", "entity_type", "AssetType")),
        "entity_uid": resolve_column(frame, ("EntityUid", "entity_uid", "AssetId")),
        "relationship": resolve_column(frame, ("RelationshipType", "Relation", "Role"), False),
    }


def _bulk_order_ids(frame: pl.DataFrame, columns, maximum: int) -> set[str]:
    work_order_column = columns["work_order"]
    entity_type_column = columns["entity_type"]
    entity_uid_column = columns["entity_uid"]
    links = frame.select(
        pl.col(work_order_column).str.strip_chars().alias("work_order_id"),
        pl.col(entity_type_column).str.strip_chars().alias("entity_type"),
        pl.col(entity_uid_column).str.strip_chars().alias("entity_uid"),
    ).filter(
        _valid_identifier_expression("work_order_id")
        & _valid_identifier_expression("entity_type")
        & _valid_identifier_expression("entity_uid", allow_zero=True)
    )
    rows = (
        links.select(
            "work_order_id",
            pl.concat_str(
                pl.col("entity_type").str.to_uppercase().str.replace_all(r"\s+", "_"),
                pl.lit(":"),
                pl.col("entity_uid").str.to_uppercase(),
            ).alias("asset_key"),
        )
        .group_by("work_order_id")
        .agg(pl.col("asset_key").n_unique().alias("asset_count"))
        .filter(pl.col("asset_count") > maximum)
        .select("work_order_id")
        .to_series()
        .to_list()
    )
    return {str(value).strip() for value in rows if value is not None}


def _valid_identifier_expression(column: str, *, allow_zero: bool = False) -> pl.Expr:
    invalid = ["", "null", "none", "nan"]
    if not allow_zero:
        invalid.append("0")
    return pl.col(column).is_not_null() & ~pl.col(column).str.to_lowercase().is_in(invalid)


def _entity_candidates(frame, columns, bulk_orders):
    entities: dict[tuple[str, str], RawEntity] = {}
    rejected = 0
    bulk_links = 0
    for row in frame.iter_rows(named=True):
        work_order_id = row.get(columns["work_order"])
        entity_type = row.get(columns["entity_type"])
        entity_uid = row.get(columns["entity_uid"])
        if str(work_order_id).strip() in bulk_orders:
            bulk_links += 1
            continue
        if not valid_identifier(work_order_id) or not valid_identifier(entity_type):
            rejected += 1
            continue
        if not valid_identifier(entity_uid, allow_zero=True):
            rejected += 1
            continue
        asset_key = build_asset_key(entity_type, entity_uid)
        key = (str(work_order_id).strip(), asset_key)
        candidate = RawEntity(
            work_order_id=key[0],
            entity_type=str(entity_type).strip(),
            entity_uid=str(entity_uid).strip(),
            relationship_type=_value(row, columns["relationship"], "primary"),
        )
        if key in entities:
            rejected += 1
            if _relationship_priority(candidate.relationship_type) > _relationship_priority(
                entities[key].relationship_type
            ):
                entities[key] = candidate
            continue
        entities[key] = candidate
    return entities, rejected, bulk_links


def _relationship_priority(value: str) -> int:
    normalized = value.lower()
    if normalized in PRIMARY_RELATIONSHIP_TYPES:
        return 2
    if normalized in FALLBACK_RELATIONSHIP_TYPES:
        return 1
    return 0


def _normalize_comments(frame: pl.DataFrame) -> tuple[list[CanonicalComment], int]:
    columns = _comment_columns(frame)
    raw_texts = [_value(row, columns["text"]) for row in frame.iter_rows(named=True)]
    repeated = deduplicate_boilerplate(raw_texts)
    comments: dict[str, CanonicalComment] = {}
    rejected = 0
    for index, row in enumerate(frame.iter_rows(named=True), start=1):
        comment = _canonical_comment(row, columns, repeated, index)
        if comment is None or comment.comment_id in comments:
            rejected += 1
            continue
        comments[comment.comment_id] = comment
    return sorted(
        comments.values(),
        key=lambda item: (item.work_order_id, item.source_sequence, item.comment_id),
    ), rejected


def _comment_columns(frame: pl.DataFrame) -> dict[str, str | None]:
    return {
        "id": resolve_column(frame, ("CommentId", "comment_id", "Id"), False),
        "work_order": resolve_column(frame, ("WorkOrderId", "work_order_id", "WOID")),
        "date": resolve_column(frame, ("DateCreated", "CreatedDate", "CommentDate", "Date"), False),
        "text": resolve_column(frame, ("Comments", "Comment", "CommentText", "Text", "Notes")),
        "type": resolve_column(frame, ("ActivityType", "CommentType", "SourceType", "Type"), False),
    }


def _canonical_comment(row, columns, repeated, index) -> CanonicalComment | None:
    work_order_id = row.get(columns["work_order"])
    raw_text = _value(row, columns["text"])
    normalized = re.sub(r"\W+", " ", raw_text.lower()).strip()
    if not valid_identifier(work_order_id) or not raw_text:
        return None
    clean_text = "" if normalized in repeated else clean_comment(raw_text)
    redaction = redact_pii(clean_text)
    identifier = row.get(columns["id"]) if columns["id"] else None
    comment_id = str(identifier).strip() if valid_identifier(identifier) else f"COMMENT-{index}"
    return CanonicalComment(
        comment_id=comment_id,
        work_order_id=str(work_order_id).strip(),
        created_at=parse_timestamp(row.get(columns["date"])) if columns["date"] else None,
        raw_text=raw_text,
        clean_text=clean_text,
        redacted_text=redaction.text,
        was_redacted=redaction.was_redacted,
        is_meaningful=bool(clean_text),
        source_type=_value(row, columns["type"], "cityworks_comment"),
        source_sequence=_sequence(identifier, index),
    )


def _sequence(value: object, fallback: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def _normalized_label(value: str, *, uppercase: bool = False) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact.upper() if uppercase else compact.title()


def _normalized_name(value: str | None) -> str:
    return value.lower().replace("_", "") if value else ""


def _as_bool(value: object) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _value(row: dict[str, object], column: str | None, default: str = "") -> str:
    if not column or row.get(column) is None:
        return default
    return str(row[column]).strip() or default
