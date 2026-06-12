"""Pydantic-Schemas für die Dashboard-API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from database.models import JobStatus


class JobOut(BaseModel):
    """Listenansicht einer Stelle."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    title: str
    url: str
    source: str
    location: str
    remote: bool
    language: str
    keyword_score: int | None
    llm_score: int | None
    match_score: int | None
    status: JobStatus
    found_at: datetime
    applied: bool
    applied_at: datetime | None
    response_received: bool
    error: str | None
    screenshot_path: str | None


class JobDetailOut(JobOut):
    """Detailansicht inklusive Beschreibung und Anschreiben."""

    description: str
    cover_letter: str | None


class StatsOut(BaseModel):
    total: int
    matched: int
    applied: int
    responses: int
    average_score: float | None
    by_status: dict[str, int]
    by_source: dict[str, int]


class StatusUpdateIn(BaseModel):
    status: JobStatus


class ActionOut(BaseModel):
    started: bool
    detail: str
