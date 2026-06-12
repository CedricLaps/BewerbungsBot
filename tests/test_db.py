"""Tests für die SQLite-Engine-Konfiguration (Mehrprozess-Tauglichkeit)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from database.db import build_session_factory


def test_file_engine_sets_busy_timeout_and_wal(tmp_path: Path) -> None:
    factory = build_session_factory(str(tmp_path / "test.db"))
    with factory() as session:
        busy_timeout = session.execute(text("PRAGMA busy_timeout")).scalar_one()
        journal_mode = str(session.execute(text("PRAGMA journal_mode")).scalar_one()).lower()
    assert busy_timeout == 30_000
    assert journal_mode == "wal"


def test_two_factories_can_write_same_database(tmp_path: Path) -> None:
    """Simuliert zwei Prozesse: beide Engines schreiben nacheinander ohne Lock-Fehler."""
    db_path = str(tmp_path / "shared.db")
    first = build_session_factory(db_path)
    second = build_session_factory(db_path)
    with first() as session:
        session.execute(
            text(
                "INSERT INTO jobs (company, title, url, source, location, remote, language, "
                "description, status, found_at, applied, response_received) "
                "VALUES ('A', 'T', 'http://a', 's', '', 0, '', '', 'NEW', "
                "CURRENT_TIMESTAMP, 0, 0)"
            )
        )
        session.commit()
    with second() as session:
        count = session.execute(text("SELECT COUNT(*) FROM jobs")).scalar_one()
        session.execute(text("UPDATE jobs SET title = 'U'"))
        session.commit()
    assert count == 1
