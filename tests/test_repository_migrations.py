from app.models.repository import SqlAlchemyRepository
from sqlalchemy import inspect, text


def test_create_schema_migrates_legacy_asset_and_comment_columns(tmp_path) -> None:
    repository = SqlAlchemyRepository(f"duckdb:///{tmp_path / 'legacy.duckdb'}")
    with repository.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE assets (asset_key VARCHAR PRIMARY KEY, entity_type VARCHAR, "
                "entity_uid VARCHAR, department VARCHAR, risk_score INTEGER, risk_reasons JSON)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO assets VALUES ('ADDRESSES:1', 'ADDRESSES', '1', 'WATER', 0, '[]')"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE comments (comment_id VARCHAR PRIMARY KEY, work_order_id VARCHAR, "
                "created_at TIMESTAMP, raw_text VARCHAR, clean_text VARCHAR, "
                "redacted_text VARCHAR, was_redacted BOOLEAN, is_meaningful BOOLEAN, "
                "source_type VARCHAR)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO comments VALUES "
                "('10', 'WO-1', NULL, '', '', '', false, false, 'legacy'), "
                "('2', 'WO-1', NULL, '', '', '', false, false, 'legacy')"
            )
        )

    repository.create_schema()

    schema = inspect(repository.engine)
    assert "asset_class" in {column["name"] for column in schema.get_columns("assets")}
    assert "source_sequence" in {
        column["name"] for column in schema.get_columns("comments")
    }
    with repository.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT asset_class FROM assets")).scalar_one()
            == "location"
        )
        ordering = connection.execute(
            text("SELECT comment_id FROM comments ORDER BY source_sequence, comment_id")
        ).scalars()
        assert list(ordering) == ["2", "10"]
