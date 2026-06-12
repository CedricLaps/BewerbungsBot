"""Tests für Pipeline-Aktionen (Anschreiben-Neugenerierung)."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.config import AppConfig
from backend.llm_client import LLMClient, LLMUnavailableError
from backend.pipeline import Pipeline


def make_pipeline(config: AppConfig, session_factory: sessionmaker[Session]) -> Pipeline:
    return Pipeline(config, session_factory)


def add_job(pipeline: Pipeline) -> int:
    job_id = pipeline.repository.add_job(
        company="Acme GmbH",
        title="Java Developer",
        url="https://example.com/jobs/1",
        source="linkedin",
        description="Java und Spring Boot",
    )
    assert job_id is not None
    return job_id


def test_regenerate_cover_letter_overwrites_existing(
    config: AppConfig,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = make_pipeline(config, session_factory)
    job_id = add_job(pipeline)
    pipeline.repository.save_cover_letter(job_id, "Altes Anschreiben ohne Stil.")
    monkeypatch.setattr(
        LLMClient,
        "generate_cover_letter",
        lambda self, t, c, d: "Neues Anschreiben im eigenen Stil.",
    )
    assert pipeline.regenerate_cover_letter(job_id) == "ok"
    job = pipeline.repository.get(job_id)
    assert job is not None
    assert job.cover_letter == "Neues Anschreiben im eigenen Stil."


def test_regenerate_cover_letter_handles_offline_llm(
    config: AppConfig,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = make_pipeline(config, session_factory)
    job_id = add_job(pipeline)
    pipeline.repository.save_cover_letter(job_id, "Altes Anschreiben.")

    def raise_unavailable(self: LLMClient, t: str, c: str, d: str) -> str:
        raise LLMUnavailableError("offline")

    monkeypatch.setattr(LLMClient, "generate_cover_letter", raise_unavailable)
    assert pipeline.regenerate_cover_letter(job_id) == "failed"
    job = pipeline.repository.get(job_id)
    assert job is not None
    # Altes Anschreiben bleibt erhalten, Fehler ist dokumentiert
    assert job.cover_letter == "Altes Anschreiben."
    assert job.error is not None


def test_regenerate_cover_letter_unknown_job(
    config: AppConfig, session_factory: sessionmaker[Session]
) -> None:
    pipeline = make_pipeline(config, session_factory)
    assert pipeline.regenerate_cover_letter(99999) == "not_found"
