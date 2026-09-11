from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock
from typing import Protocol

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from app.data.validators import classify_asset
from app.models.database import Base

DATABASE_WRITE_LOCK = RLock()


class Repository(Protocol):
    @contextmanager
    def session(self) -> Iterator[Session]: ...

    def create_schema(self) -> None: ...


class SqlAlchemyRepository:
    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_engine(database_url)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._migrate_legacy_columns()

    def _migrate_legacy_columns(self) -> None:
        schema = inspect(self.engine)
        tables = set(schema.get_table_names())
        with self.engine.begin() as connection:
            if "assets" in tables and not _has_column(schema, "assets", "asset_class"):
                connection.execute(
                    text("ALTER TABLE assets ADD COLUMN asset_class VARCHAR DEFAULT 'equipment'")
                )
                assets = connection.execute(text("SELECT asset_key, entity_type FROM assets")).all()
                if assets:
                    connection.execute(
                        text(
                            "UPDATE assets SET asset_class = :asset_class "
                            "WHERE asset_key = :asset_key"
                        ),
                        [
                            {"asset_key": key, "asset_class": classify_asset(entity_type)}
                            for key, entity_type in assets
                        ],
                    )
            if "comments" in tables and not _has_column(schema, "comments", "source_sequence"):
                connection.execute(
                    text("ALTER TABLE comments ADD COLUMN source_sequence INTEGER DEFAULT 0")
                )
                comments = connection.execute(
                    text(
                        "SELECT comment_id FROM comments "
                        "ORDER BY work_order_id, created_at, comment_id"
                    )
                ).scalars()
                updates = [
                    {
                        "comment_id": comment_id,
                        "source_sequence": _source_sequence(comment_id, index),
                    }
                    for index, comment_id in enumerate(comments, start=1)
                ]
                if updates:
                    connection.execute(
                        text(
                            "UPDATE comments SET source_sequence = :source_sequence "
                            "WHERE comment_id = :comment_id"
                        ),
                        updates,
                    )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = Session(self.engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _has_column(schema, table: str, column: str) -> bool:
    return column in {item["name"] for item in schema.get_columns(table)}


def _source_sequence(comment_id: object, fallback: int) -> int:
    try:
        return int(str(comment_id))
    except (TypeError, ValueError):
        return fallback
