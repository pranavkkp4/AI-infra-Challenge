import os
from pathlib import Path

import polars as pl
import pytest
from app.data.normalizer import normalize_source
from app.data.pii import redact_pii
from app.data.validators import classify_asset

from scripts.import_starter_data import EXPECTED_FILES, import_starter_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STARTER_DATA = PROJECT_ROOT / "data" / "raw"


def _write_source(root: Path, work_orders, entities, comments) -> Path:
    data_dir = root / "data"
    data_dir.mkdir()
    pl.DataFrame(work_orders).write_csv(data_dir / "WORKORDER.csv")
    pl.DataFrame(entities).write_csv(data_dir / "WOENTITY.csv")
    pl.DataFrame(comments).write_csv(data_dir / "WOCOMMENT.csv")
    return root


def _work_order(identifier: str) -> dict[str, object]:
    return {
        "WorkOrderId": identifier,
        "InitiateDate": "2009-04-08T07:00:00Z",
        "Description": "Template label only",
        "Shop": "WATER",
        "AssetGroup": "Water Distribution",
        "Priority": "3",
        "WOAddress": "100 Main St",
        "Location": "North pressure zone",
        "Status": "CLOSED",
        "IsReactive": "True",
        "Text10": "route-a",
        "ApplyToEntity": "CITYFACILITIES",
    }


def _comment(identifier: str, work_order_id: str, text: str) -> dict[str, str]:
    return {
        "CommentId": identifier,
        "WorkOrderId": work_order_id,
        "Comments": text,
        "DateCreated": "1970-01-01T07:00:00Z",
        "ActivityType": "2",
    }


def test_official_schema_composite_keys_cleaning_and_comment_order(tmp_path) -> None:
    source = _write_source(
        tmp_path,
        [_work_order("100"), _work_order("101")],
        [
            {
                "WorkOrderId": "100",
                "EntityType": "PUMP",
                "EntityUid": "0",
                "RelationshipType": "attached",
            },
            {"WorkOrderId": "100", "EntityType": "CITYFACILITIES", "EntityUid": "642"},
            {"WorkOrderId": "101", "EntityType": "VALVE", "EntityUid": "0"},
        ],
        [
            _comment("20", "100", "By MOORE, CYNTHIA: pump repaired complete"),
            _comment(
                "3",
                "100",
                "From: Request ID: 17, 04/08/2009\nProblem Details:\n"
                "Problem Comments: water leak at pump\nBy JACKSON, JACKIE: inspected leak",
            ),
            _comment("30", "101", "Meter problem dispatched to Mike Neal"),
        ],
    )

    dataset = normalize_source(source)
    by_id = {order.work_order_id: order for order in dataset.work_orders}
    ordered = [
        item.source_sequence for item in dataset.comments if item.work_order_id == "100"
    ]
    redacted = " ".join(item.redacted_text for item in dataset.comments)

    assert set(by_id) == {"100", "101"}
    assert by_id["100"].asset_keys == ["PUMP:0"]
    assert by_id["101"].asset_keys == ["VALVE:0"]
    assert by_id["100"].metadata["site"] == "100 Main St"
    assert by_id["100"].metadata["is_reactive"] is True
    assert by_id["100"].metadata["analysis_eligible"] is True
    assert ordered == [3, 20]
    assert "From: Request ID" not in redacted
    assert "JACKSON" not in redacted and "CYNTHIA" not in redacted
    assert all(comment.created_at is None for comment in dataset.comments)
    assert {comment.source_type for comment in dataset.comments} == {"2"}
    assert dataset.report.excluded_rows["catch_all_entity_links"] == 1
    assert classify_asset("ADDRESSES") == "location"
    assert classify_asset("CITY_DEPTS") == "location"
    assert classify_asset("WHYDRANT") == "equipment"


def test_official_inventory_sweep_is_excluded_before_analysis(tmp_path) -> None:
    work_orders = [
        _work_order("bulk"),
        _work_order("duplicate"),
        _work_order("invalid-heavy"),
        _work_order("usable"),
    ]
    entities = [
        {"WorkOrderId": "bulk", "EntityType": "VALVE", "EntityUid": str(index)}
        for index in range(11)
    ]
    entities.extend(
        {"WorkOrderId": "duplicate", "EntityType": "VALVE", "EntityUid": "20"}
        for _ in range(11)
    )
    entities.append(
        {"WorkOrderId": "invalid-heavy", "EntityType": "PUMP", "EntityUid": "30"}
    )
    entities.extend(
        {"WorkOrderId": "invalid-heavy", "EntityType": "", "EntityUid": str(index)}
        for index in range(11)
    )
    entities.append({"WorkOrderId": "usable", "EntityType": "VALVE", "EntityUid": "21"})
    comments = [
        _comment("1", "bulk", "inventory sweep of valves"),
        _comment("2", "duplicate", "water leak at service valve"),
        _comment("3", "invalid-heavy", "pump failure with invalid attachments"),
        _comment("4", "usable", "water leak at service valve"),
    ]

    dataset = normalize_source(_write_source(tmp_path, work_orders, entities, comments))

    assert [order.work_order_id for order in dataset.work_orders] == [
        "duplicate",
        "invalid-heavy",
        "usable",
    ]
    assert dataset.report.excluded_rows["bulk_work_orders"] == 1
    assert dataset.report.excluded_rows["bulk_entity_links"] == 11


def test_starter_zip_import_is_flattened_into_ignored_raw_directory(tmp_path) -> None:
    from zipfile import ZipFile

    starter = tmp_path / "starter" / "data"
    starter.mkdir(parents=True)
    with ZipFile(starter / "data.zip", "w") as archive:
        archive.writestr(
            "data/WORKORDER.csv", "WorkOrderId,InitiateDate\n1,2009-01-01\n"
        )
        archive.writestr(
            "data/WOENTITY.csv", "WorkOrderId,EntityType,EntityUid\n1,PUMP,1\n"
        )
        archive.writestr("data/WOCOMMENT.csv", "WorkOrderId,Comments\n1,pump leak\n")

    output = tmp_path / "raw"
    output.mkdir()
    (output / ".gitkeep").write_text("", encoding="utf-8")
    sizes = import_starter_data(starter.parent, output)

    assert set(sizes) == set(EXPECTED_FILES)
    assert all((output / name).is_file() for name in EXPECTED_FILES)
    assert (output / ".gitkeep").is_file()


def test_normalized_headers_and_maintenance_prose_are_preserved(tmp_path) -> None:
    source = _write_source(
        tmp_path,
        [
            {
                "WORK_ORDER_ID": "normalized",
                "INITIATE_DATE": "2009-04-08T07:00:00Z",
            }
        ],
        [
            {
                "WORK_ORDER_ID": "normalized",
                "ENTITY_TYPE": "PUMP",
                "ENTITY_UID": "20",
            }
        ],
        [
            {
                "COMMENT_ID": "1",
                "WORK_ORDER_ID": "normalized",
                "COMMENTS": "Work completed by replacing pump, restored pressure: verified",
                "ACTIVITY_TYPE": "crew-note",
            }
        ],
    )

    dataset = normalize_source(source)

    assert dataset.work_orders[0].work_order_id == "normalized"
    assert dataset.comments[0].source_type == "crew-note"
    assert "replacing pump" in dataset.comments[0].redacted_text
    assert not redact_pii(
        "Work completed by replacing pump, restored pressure: verified"
    ).was_redacted
    assert "MIKE NEAL" not in redact_pii("DISPATCHED TO MIKE NEAL").text
    assert not redact_pii("by REPLACING PUMP, RESTORED PRESSURE: verified").was_redacted


def test_explicit_primary_assets_outrank_attached_context(tmp_path) -> None:
    source = _write_source(
        tmp_path,
        [_work_order("mixed")],
        [
            {
                "WorkOrderId": "mixed",
                "EntityType": "PUMP",
                "EntityUid": "20",
                "RelationshipType": "primary",
            },
            {
                "WorkOrderId": "mixed",
                "EntityType": "ADDRESSES",
                "EntityUid": "100",
                "RelationshipType": "attached",
            },
        ],
        [_comment("1", "mixed", "pump failure")],
    )

    order = normalize_source(source).work_orders[0]

    assert order.asset_keys == ["ADDRESSES:100", "PUMP:20"]
    assert order.primary_asset_keys == ["PUMP:20"]


@pytest.mark.parametrize(
    "relationships", [("attached", "appliesto"), ("appliesto", "attached")]
)
def test_duplicate_relationships_preserve_primary_precedence(
    tmp_path, relationships
) -> None:
    source = _write_source(
        tmp_path,
        [_work_order("duplicate-role")],
        [
            {
                "WorkOrderId": "duplicate-role",
                "EntityType": "PUMP",
                "EntityUid": "20",
                "RelationshipType": relationship,
            }
            for relationship in relationships
        ],
        [_comment("1", "duplicate-role", "pump failure")],
    )

    dataset = normalize_source(source)

    assert dataset.work_orders[0].primary_asset_keys == ["PUMP:20"]
    assert dataset.entities[0].relationship_type.lower() == "appliesto"


def test_administrative_notes_are_retained_but_not_analyzed(tmp_path) -> None:
    source = _write_source(
        tmp_path,
        [_work_order("admin")],
        [{"WorkOrderId": "admin", "EntityType": "FACILITY", "EntityUid": "20"}],
        [_comment("1", "admin", "JANITORIAL SUPPLIES FM - Janitorial Supply Order")],
    )

    dataset = normalize_source(source)

    assert not dataset.work_orders[0].metadata["analysis_eligible"]
    assert dataset.report.excluded_rows["non_maintenance_work_orders"] == 1


def test_failed_archive_import_does_not_replace_existing_files(tmp_path) -> None:
    from zipfile import ZipFile

    starter = tmp_path / "starter"
    output = tmp_path / "raw"
    starter.mkdir()
    output.mkdir()
    for name in EXPECTED_FILES:
        (output / name).write_text("existing\n", encoding="utf-8")
    with ZipFile(starter / "data.zip", "w") as archive:
        archive.writestr("data/WORKORDER.csv", "replacement\n")

    with pytest.raises(FileNotFoundError):
        import_starter_data(starter, output)

    assert all(
        (output / name).read_text(encoding="utf-8") == "existing\n"
        for name in EXPECTED_FILES
    )


def test_invalid_csv_import_does_not_replace_existing_files(tmp_path) -> None:
    starter = tmp_path / "starter"
    output = tmp_path / "raw"
    starter.mkdir()
    output.mkdir()
    for name in EXPECTED_FILES:
        (output / name).write_text("existing\n", encoding="utf-8")
    for name, columns in {
        "WORKORDER.csv": "WorkOrderId,InitiateDate",
        "WOENTITY.csv": "WorkOrderId,EntityType,EntityUid",
        "WOCOMMENT.csv": "WorkOrderId,Comments",
    }.items():
        (starter / name).write_text(f"{columns}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not contain any data rows"):
        import_starter_data(starter, output)

    assert all(
        (output / name).read_text(encoding="utf-8") == "existing\n"
        for name in EXPECTED_FILES
    )


@pytest.mark.skipif(
    os.getenv("CIVICOPS_RUN_STARTER_SMOKE") != "1",
    reason="Set CIVICOPS_RUN_STARTER_SMOKE=1 after extracting the official starter data.",
)
def test_full_official_starter_dataset_smoke() -> None:
    dataset = normalize_source(STARTER_DATA)

    assert dataset.report.source_rows == {
        "WORKORDER.csv": 37_778,
        "WOENTITY.csv": 867_448,
        "WOCOMMENT.csv": 33_572,
    }
    assert len(dataset.work_orders) == 27_605
    assert (
        len({asset for order in dataset.work_orders for asset in order.asset_keys})
        == 26_413
    )
    assert (
        sum(order.metadata["analysis_eligible"] for order in dataset.work_orders)
        == 23_744
    )
    assert dataset.report.excluded_rows["non_maintenance_work_orders"] == 57
    assert "CITYFACILITIES:642" not in {
        asset for order in dataset.work_orders for asset in order.asset_keys
    }
    assert sum(comment.was_redacted for comment in dataset.comments) == 22_174
