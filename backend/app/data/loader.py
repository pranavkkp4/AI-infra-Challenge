from pathlib import Path

import polars as pl

EXPECTED_FILES = ("WORKORDER.csv", "WOENTITY.csv", "WOCOMMENT.csv")


def load_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required source file not found: {path}")
    return pl.read_csv(
        path,
        infer_schema=False,
        null_values=["", "NULL", "null", "None"],
    )


def load_source_frames(source_dir: Path) -> dict[str, pl.DataFrame]:
    return {name: load_csv(source_dir / name) for name in EXPECTED_FILES}


def resolve_column(
    frame: pl.DataFrame, candidates: tuple[str, ...], required: bool = True
) -> str | None:
    by_normalized = {column.lower().replace("_", ""): column for column in frame.columns}
    for candidate in candidates:
        match = by_normalized.get(candidate.lower().replace("_", ""))
        if match:
            return match
    if required:
        raise ValueError(
            f"Missing required column. Expected one of {candidates}; found {frame.columns}"
        )
    return None
