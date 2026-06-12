"""Tests für das Repository: Duplikate, Statuswechsel, Filter, Statistiken."""
from __future__ import annotations

from database.models import JobStatus
from database.repository import JobFilter, JobRepository


def add_sample_job(repository: JobRepository, **overrides: object) -> int:
    defaults: dict[str, object] = {
        "company": "Acme GmbH",
        "title": "Java Developer",
        "url": "https://example.com/jobs/1",
        "source": "greenhouse",
        "location": "Berlin, Deutschland",
        "description": "Java und Spring Boot",
        "remote": False,
    }
    defaults.update(overrides)
    job_id = repository.add_job(**defaults)  # type: ignore[arg-type]
    assert job_id is not None
    return job_id


def test_add_job_returns_id(repository: JobRepository) -> None:
    job_id = add_sample_job(repository)
    job = repository.get(job_id)
    assert job is not None
    assert job.status is JobStatus.NEW


def test_duplicate_url_is_rejected(repository: JobRepository) -> None:
    add_sample_job(repository)
    duplicate = repository.add_job(
        company="Andere Firma",
        title="Anderer Titel",
        url="https://example.com/jobs/1",
        source="lever",
    )
    assert duplicate is None


def test_duplicate_company_title_location_is_rejected(repository: JobRepository) -> None:
    add_sample_job(repository)
    duplicate = repository.add_job(
        company="Acme GmbH",
        title="Java Developer",
        url="https://andere-url.example.com/jobs/99",
        source="linkedin",
        location="Berlin, Deutschland",
    )
    assert duplicate is None


def test_set_score_marks_matched_above_threshold(repository: JobRepository) -> None:
    job_id = add_sample_job(repository)
    repository.set_score(
        job_id, keyword_score=70, llm_score=80, match_score=75, language="de", min_match_score=60
    )
    job = repository.get(job_id)
    assert job is not None
    assert job.status is JobStatus.MATCHED
    assert job.match_score == 75


def test_set_score_marks_skipped_below_threshold(repository: JobRepository) -> None:
    job_id = add_sample_job(repository)
    repository.set_score(
        job_id, keyword_score=30, llm_score=None, match_score=30, language="en", min_match_score=60
    )
    job = repository.get(job_id)
    assert job is not None
    assert job.status is JobStatus.SKIPPED


def test_jobs_to_apply_only_returns_matched_unapplied(repository: JobRepository) -> None:
    matched_id = add_sample_job(repository, url="https://example.com/jobs/a")
    repository.set_score(
        matched_id, keyword_score=80, llm_score=None, match_score=80, language="de", min_match_score=60
    )
    skipped_id = add_sample_job(repository, url="https://example.com/jobs/b", title="Backend Engineer")
    repository.set_score(
        skipped_id, keyword_score=20, llm_score=None, match_score=20, language="de", min_match_score=60
    )
    candidates = repository.jobs_to_apply(min_score=60, limit=10)
    assert [job.id for job in candidates] == [matched_id]


def test_mark_applied_sets_flags(repository: JobRepository) -> None:
    job_id = add_sample_job(repository)
    repository.mark_applied(job_id, screenshot_path="logs/screenshots/test.png")
    job = repository.get(job_id)
    assert job is not None
    assert job.applied is True
    assert job.applied_at is not None
    assert job.status is JobStatus.APPLIED


def test_mark_failed_keeps_applied_false(repository: JobRepository) -> None:
    job_id = add_sample_job(repository)
    repository.mark_failed(job_id, "Formular nicht gefunden")
    job = repository.get(job_id)
    assert job is not None
    assert job.applied is False
    assert job.status is JobStatus.FAILED
    assert job.error == "Formular nicht gefunden"


def test_update_status_to_interview_marks_response(repository: JobRepository) -> None:
    job_id = add_sample_job(repository)
    repository.update_status(job_id, JobStatus.INTERVIEW)
    job = repository.get(job_id)
    assert job is not None
    assert job.response_received is True
    assert job.response_at is not None


def test_list_jobs_filters_remote(repository: JobRepository) -> None:
    add_sample_job(repository, url="https://example.com/jobs/r1", remote=True, title="Remote Java Dev")
    add_sample_job(repository, url="https://example.com/jobs/o1", remote=False, title="Office Java Dev")
    remote_jobs = repository.list_jobs(JobFilter(remote=True))
    assert len(remote_jobs) == 1
    assert remote_jobs[0].remote is True


def test_list_jobs_filters_germany_region(repository: JobRepository) -> None:
    add_sample_job(repository, url="https://example.com/jobs/de", location="München, Deutschland")
    add_sample_job(
        repository, url="https://example.com/jobs/us", location="New York, USA", title="Backend Engineer"
    )
    german_jobs = repository.list_jobs(JobFilter(region="germany"))
    assert len(german_jobs) == 1
    assert "Deutschland" in german_jobs[0].location or "München" in german_jobs[0].location


def test_list_jobs_text_search(repository: JobRepository) -> None:
    add_sample_job(repository, url="https://example.com/jobs/ng", description="Angular Frontend und Java")
    add_sample_job(
        repository, url="https://example.com/jobs/py", description="Nur Python", title="Software Engineer"
    )
    angular_jobs = repository.list_jobs(JobFilter(text="angular"))
    assert len(angular_jobs) == 1


def test_stats_counts(repository: JobRepository) -> None:
    first = add_sample_job(repository, url="https://example.com/jobs/s1")
    repository.set_score(
        first, keyword_score=80, llm_score=None, match_score=80, language="de", min_match_score=60
    )
    repository.mark_applied(first)
    add_sample_job(repository, url="https://example.com/jobs/s2", title="Backend Engineer")
    stats = repository.stats()
    assert stats["total"] == 2
    assert stats["applied"] == 1
    assert stats["by_source"]["greenhouse"] == 2
    assert stats["average_score"] == 80.0
