"""Engine- und Session-Verwaltung für SQLite."""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base

_BUSY_TIMEOUT_MS = 30_000


def _configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
    """WAL-Modus und Busy-Timeout, damit mehrere Prozesse (Dashboard, Scheduler,
    CLI) gleichzeitig schreiben können, statt mit 'database is locked' abzubrechen."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def build_engine(database_path: str) -> Engine:
    """Erzeugt eine SQLite-Engine; ':memory:' wird für Tests unterstützt."""
    if database_path == ":memory:":
        return create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": _BUSY_TIMEOUT_MS / 1000},
    )
    event.listen(engine, "connect", _configure_sqlite)
    return engine


def build_session_factory(database_path: str) -> sessionmaker[Session]:
    """Initialisiert Schema und liefert eine Session-Factory."""
    engine = build_engine(database_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transaktionaler Session-Kontext: commit bei Erfolg, rollback bei Fehlern."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
