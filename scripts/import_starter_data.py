#!/usr/bin/env python3
import argparse
import csv
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

EXPECTED_FILES = ("WORKORDER.csv", "WOENTITY.csv", "WOCOMMENT.csv")
REQUIRED_COLUMNS = {
    "WORKORDER.csv": {"WorkOrderId", "InitiateDate"},
    "WOENTITY.csv": {"WorkOrderId", "EntityType", "EntityUid"},
    "WOCOMMENT.csv": {"WorkOrderId", "Comments"},
}


def import_starter_data(starter: Path, output: Path) -> dict[str, int]:
    source = starter / "data" if (starter / "data").is_dir() else starter
    archive = source / "data.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="civicops-import-", dir=output.parent) as temporary:
        temporary_root = Path(temporary)
        staging = temporary_root / "replacement"
        if output.exists():
            shutil.copytree(output, staging)
        else:
            staging.mkdir()
        if archive.exists():
            _extract_archive(archive, staging)
        else:
            _copy_expanded_files(source, staging)
        _validate_import(staging)
        _replace_directory(staging, output, temporary_root / "previous")
    return {name: (output / name).stat().st_size for name in EXPECTED_FILES}


def _validate_import(staging: Path) -> None:
    missing = [name for name in EXPECTED_FILES if not (staging / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Starter source is missing: {', '.join(missing)}")
    for name in EXPECTED_FILES:
        _validate_csv(staging / name, REQUIRED_COLUMNS[name])


def _validate_csv(path: Path, required_columns: set[str]) -> None:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        missing = sorted(required_columns - set(header))
        if missing:
            raise ValueError(
                f"{path.name} is missing required columns: {', '.join(missing)}"
            )
        if next(reader, None) is None:
            raise ValueError(f"{path.name} does not contain any data rows")


def _replace_directory(staging: Path, output: Path, backup: Path) -> None:
    if output.exists():
        output.replace(backup)
    try:
        staging.replace(output)
    except Exception:
        if backup.exists():
            backup.replace(output)
        raise


def _extract_archive(archive_path: Path, output: Path) -> None:
    with ZipFile(archive_path) as archive:
        members = {Path(name).name: name for name in archive.namelist()}
        for expected in EXPECTED_FILES:
            member = members.get(expected)
            if member is None:
                raise FileNotFoundError(f"{archive_path} does not contain {expected}")
            with (
                archive.open(member) as source,
                (output / expected).open("wb") as target,
            ):
                shutil.copyfileobj(source, target)


def _copy_expanded_files(source: Path, output: Path) -> None:
    for name in EXPECTED_FILES:
        source_file = source / name
        if not source_file.is_file():
            raise FileNotFoundError(f"Required starter file not found: {source_file}")
        shutil.copy2(source_file, output / name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the official AI4Infra starter data"
    )
    parser.add_argument(
        "--starter", type=Path, required=True, help="Starter repository or data/"
    )
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    sizes = import_starter_data(args.starter, args.output)
    for name, size in sizes.items():
        print(f"{name}: {size:,} bytes")


if __name__ == "__main__":
    main()
