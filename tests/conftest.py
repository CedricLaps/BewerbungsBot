"""Gemeinsame Fixtures: Test-Konfiguration und In-Memory-Datenbank."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.config import AppConfig
from database.db import build_session_factory
from database.repository import JobRepository


@pytest.fixture()
def config() -> AppConfig:
    return AppConfig(
        email="test@example.com",
        phone="+49 123 456789",
        linkedin="https://www.linkedin.com/in/test",
        database_path=":memory:",
        scheduler_enabled=False,
    )


@pytest.fixture()
def session_factory() -> sessionmaker[Session]:
    return build_session_factory(":memory:")


@pytest.fixture()
def repository(session_factory: sessionmaker[Session]) -> JobRepository:
    return JobRepository(session_factory)


class FakeResponse:
    """Minimaler Ersatz für requests.Response in LLM- und Scraper-Tests."""

    def __init__(self, status_code: int = 200, json_data: object = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.content = text.encode("utf-8")

    def json(self) -> object:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def fake_response_class() -> type[FakeResponse]:
    return FakeResponse
