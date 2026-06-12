"""Tests für den ApplyManager: Applier-Auswahl, Anschreiben, Manuell-Status,
LinkedIn-Zielauflösung und Absende-Limit."""
from __future__ import annotations

import pytest

import apply.manager as manager_module
from apply.base import ApplicationResult
from apply.greenhouse import GreenhouseApplier
from apply.manager import ApplyManager
from backend.config import AppConfig
from backend.llm_client import LLMClient, LLMUnavailableError
from database.models import Job, JobStatus
from database.repository import JobRepository


def make_manager(config: AppConfig, repository: JobRepository) -> ApplyManager:
    return ApplyManager(config, repository, LLMClient(config))


def add_matched_job(repository: JobRepository, url: str, title: str = "Java Developer") -> int:
    job_id = repository.add_job(
        company="Acme GmbH",
        title=title,
        url=url,
        source="linkedin",
        location="Berlin",
        description="Java und Spring Boot",
    )
    assert job_id is not None
    repository.set_score(
        job_id, keyword_score=80, llm_score=None, match_score=80, language="de", min_match_score=60
    )
    return job_id


def test_find_applier_recognizes_supported_platforms(
    config: AppConfig, repository: JobRepository
) -> None:
    manager = make_manager(config, repository)
    assert manager.find_applier("https://boards.greenhouse.io/acme/jobs/1") is not None
    assert manager.find_applier("https://jobs.lever.co/acme/abc") is not None
    assert manager.find_applier("https://acme.jobs.personio.de/job/123") is not None
    assert manager.find_applier("https://acme.wd3.myworkdayjobs.com/External/job/X_R1") is not None
    assert manager.find_applier("https://de.linkedin.com/jobs/view/123") is None
    assert manager.find_applier("https://www.stepstone.de/stellenangebote--x.html") is None


def test_no_applier_generates_letter_and_marks_manual(
    config: AppConfig, repository: JobRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = add_matched_job(repository, "https://de.linkedin.com/jobs/view/4426739744")
    monkeypatch.setattr(
        LLMClient,
        "generate_cover_letter",
        lambda self, title, company, description: "Sehr geehrtes Team, individuelles Anschreiben.",
    )
    manager = make_manager(config, repository)
    job = repository.get(job_id)
    assert job is not None
    outcome = manager.apply_to_job(job)
    assert outcome == "no_applier"
    updated = repository.get(job_id)
    assert updated is not None
    assert updated.status is JobStatus.MANUAL
    assert updated.cover_letter == "Sehr geehrtes Team, individuelles Anschreiben."
    assert updated.error is not None and "anschreiben" in updated.error.lower()


def test_no_applier_with_offline_llm_keeps_job_matched(
    config: AppConfig, repository: JobRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = add_matched_job(repository, "https://de.linkedin.com/jobs/view/999")

    def raise_unavailable(self: LLMClient, title: str, company: str, description: str) -> str:
        raise LLMUnavailableError("offline")

    monkeypatch.setattr(LLMClient, "generate_cover_letter", raise_unavailable)
    manager = make_manager(config, repository)
    job = repository.get(job_id)
    assert job is not None
    outcome = manager.apply_to_job(job)
    assert outcome == "no_letter"
    updated = repository.get(job_id)
    assert updated is not None
    # Bleibt MATCHED, damit der nächste Lauf es erneut versucht
    assert updated.status is JobStatus.MATCHED
    assert updated.cover_letter is None


def test_linkedin_target_resolving_to_ats_triggers_auto_apply(
    config: AppConfig, repository: JobRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = add_matched_job(repository, "https://de.linkedin.com/jobs/view/4426739744")
    monkeypatch.setattr(
        LLMClient, "generate_cover_letter", lambda self, t, c, d: "Anschreiben."
    )
    monkeypatch.setattr(
        manager_module,
        "resolve_apply_target",
        lambda url: "https://boards.greenhouse.io/acme/jobs/99?gh_src=li",
    )
    monkeypatch.setattr(manager_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        GreenhouseApplier,
        "apply",
        lambda self, job, letter: ApplicationResult(
            success=True, submitted=True, message="Bewerbung abgesendet"
        ),
    )
    manager = make_manager(config, repository)
    job = repository.get(job_id)
    assert job is not None
    assert manager.apply_to_job(job) == "submitted"
    updated = repository.get(job_id)
    assert updated is not None
    assert updated.status is JobStatus.APPLIED
    assert updated.url == "https://boards.greenhouse.io/acme/jobs/99"


def test_linkedin_target_duplicate_is_skipped(
    config: AppConfig, repository: JobRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing_id = repository.add_job(
        company="Acme GmbH",
        title="Backend Developer",
        url="https://boards.greenhouse.io/acme/jobs/99",
        source="greenhouse",
        location="Hamburg",
    )
    assert existing_id is not None
    job_id = add_matched_job(repository, "https://de.linkedin.com/jobs/view/555")
    monkeypatch.setattr(
        LLMClient, "generate_cover_letter", lambda self, t, c, d: "Anschreiben."
    )
    monkeypatch.setattr(
        manager_module,
        "resolve_apply_target",
        lambda url: "https://boards.greenhouse.io/acme/jobs/99",
    )
    monkeypatch.setattr(manager_module.time, "sleep", lambda _: None)
    manager = make_manager(config, repository)
    job = repository.get(job_id)
    assert job is not None
    assert manager.apply_to_job(job) == "duplicate"
    updated = repository.get(job_id)
    assert updated is not None
    assert updated.status is JobStatus.SKIPPED


def test_run_limits_submissions_but_processes_all(
    config: AppConfig, repository: JobRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = add_matched_job(repository, "https://boards.greenhouse.io/acme/jobs/1")
    second = add_matched_job(
        repository, "https://boards.greenhouse.io/acme/jobs/2", title="Backend Engineer"
    )
    monkeypatch.setattr(
        LLMClient, "generate_cover_letter", lambda self, t, c, d: "Anschreiben."
    )
    monkeypatch.setattr(
        GreenhouseApplier,
        "apply",
        lambda self, job, letter: ApplicationResult(
            success=True, submitted=True, message="Bewerbung abgesendet"
        ),
    )
    manager = make_manager(config, repository)
    counters = manager.run(limit=1)
    assert counters["submitted"] == 1
    assert counters["deferred"] == 1
    jobs = {first: repository.get(first), second: repository.get(second)}
    statuses = {job.status for job in jobs.values() if job is not None}
    # Einer beworben, einer bleibt für den nächsten Lauf passend
    assert statuses == {JobStatus.APPLIED, JobStatus.MATCHED}
    deferred = next(job for job in jobs.values() if job and job.status is JobStatus.MATCHED)
    assert deferred.cover_letter == "Anschreiben."


def test_existing_cover_letter_is_not_regenerated(
    config: AppConfig, repository: JobRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = add_matched_job(repository, "https://de.linkedin.com/jobs/view/777")
    repository.save_cover_letter(job_id, "Bereits vorhandenes Anschreiben.")

    def fail_if_called(self: LLMClient, title: str, company: str, description: str) -> str:
        raise AssertionError("generate_cover_letter darf nicht erneut aufgerufen werden")

    monkeypatch.setattr(LLMClient, "generate_cover_letter", fail_if_called)
    manager = make_manager(config, repository)
    job = repository.get(job_id)
    assert job is not None
    assert manager.apply_to_job(job) == "no_applier"
    updated = repository.get(job_id)
    assert updated is not None
    assert updated.cover_letter == "Bereits vorhandenes Anschreiben."
