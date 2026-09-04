from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock
from typing import Protocol

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

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
