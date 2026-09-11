from pathlib import Path

import polars as pl

EXPECTED_FILES = ("WORKORDER.csv", "WOENTITY.csv", "WOCOMMENT.csv")
SOURCE_COLUMNS = {
    "WORKORDER.csv": (
        "WorkOrderId",
        "work_order_id",
        "WOID",
        "InitiateDate",
        "CreatedDate",
        "OccurredAt",
        "Date",
        "OpenDate",
        "Description",
        "Summary",
        "Title",
        "AssetGroup",
        "Category",
        "WorkType",
        "Type",
        "Shop",
        "Department",
        "Division",
        "Agency",
        "Status",
        "WorkOrderStatus",
        "Priority",
        "Severity",
        "WOAddress",
        "Address",
        "Location",
        "IsReactive",
        "Text10",
        "ApplyToEntity",
    ),
    "WOENTITY.csv": (
        "WorkOrderId",
        "work_order_id",
        "WOID",
        "EntityType",
        "entity_type",
        "AssetType",
        "EntityUid",
        "entity_uid",
        "AssetId",
        "RelationshipType",
        "Relation",
        "Role",
    ),
    "WOCOMMENT.csv": (
        "CommentId",
        "comment_id",
        "Id",
        "WorkOrderId",
        "work_order_id",
        "WOID",
        "DateCreated",
        "CreatedDate",
        "CommentDate",
        "Date",
        "Comments",
        "Comment",
        "CommentText",
        "Text",
        "Notes",
        "ActivityType",
        "CommentType",
        "SourceType",
        "Type",
    ),
}


def load_csv(path: Path, columns: tuple[str, ...]) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required source file not found: {path}")
    source = pl.scan_csv(
        path,
        infer_schema=False,
        null_values=["", "NULL", "null", "None"],
    )
    available = source.collect_schema().names()
    by_normalized = {_normalized_name(column): column for column in available}
    selected = list(
        dict.fromkeys(
            match
            for column in columns
            if (match := by_normalized.get(_normalized_name(column))) is not None
        )
    )
    return source.select(selected).collect()


def load_source_frames(source_dir: Path) -> dict[str, pl.DataFrame]:
    resolved = resolve_source_dir(source_dir)
    return {name: load_csv(resolved / name, SOURCE_COLUMNS[name]) for name in EXPECTED_FILES}


def resolve_source_dir(source_dir: Path) -> Path:
    for candidate in (source_dir, source_dir / "data"):
        if all((candidate / name).exists() for name in EXPECTED_FILES):
            return candidate
    expected = ", ".join(EXPECTED_FILES)
    raise FileNotFoundError(f"Could not find {expected} in {source_dir} or {source_dir / 'data'}")


def resolve_column(
    frame: pl.DataFrame, candidates: tuple[str, ...], required: bool = True
) -> str | None:
    by_normalized = {_normalized_name(column): column for column in frame.columns}
    for candidate in candidates:
        match = by_normalized.get(_normalized_name(candidate))
        if match:
            return match
    if required:
        raise ValueError(
            f"Missing required column. Expected one of {candidates}; found {frame.columns}"
        )
    return None


def _normalized_name(value: str) -> str:
    return value.lower().replace("_", "")
