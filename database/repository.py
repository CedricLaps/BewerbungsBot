"""Repository: alle Datenbankzugriffe inkl. Duplikatsvermeidung und Statistiken."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from database.db import session_scope
from database.models import ApplicationAttempt, Job, JobStatus, utcnow

logger = logging.getLogger(__name__)

# Ortsbegriffe für die Dashboard-Filter "Deutschland" und "Europa"
_GERMANY_TERMS: tuple[str, ...] = (
    "deutschland", "germany", "berlin", "münchen", "munich", "hamburg",
    "frankfurt", "köln", "cologne", "stuttgart", "düsseldorf", "leipzig",
    "dresden", "hannover", "nürnberg", "essen", "dortmund", "bremen",
)
_EUROPE_TERMS: tuple[str, ...] = (
    "europe", "europa", "european", "emea", "deutschland", "germany",
    "austria", "österreich", "switzerland", "schweiz", "netherlands",
    "niederlande", "france", "spain", "poland", "portugal", "remote",
)


@dataclass(frozen=True)
class JobFilter:
    """Filterkriterien für die Jobliste im Dashboard."""

    status: JobStatus | None = None
    remote: bool | None = None
    region: str | None = None  # "germany" | "europe" | None
    text: str | None = None
    min_score: int | None = None
    applied: bool | None = None
    limit: int = 200
    offset: int = 0


class JobRepository:
    """Kapselt alle CRUD-Operationen auf der SQLite-Datenbank."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    # ------------------------------------------------------------- Anlegen

    def add_job(
        self,
        *,
        company: str,
        title: str,
        url: str,
        source: str,
        location: str = "",
        description: str = "",
        remote: bool = False,
    ) -> int | None:
        """Speichert eine Stelle; gibt die neue ID zurück oder None bei Duplikat."""
        with session_scope(self._factory) as session:
            duplicate = session.execute(
                select(Job.id).where(
                    or_(
                        Job.url == url,
                        (Job.company == company) & (Job.title == title) & (Job.location == location),
                    )
                )
            ).first()
            if duplicate is not None:
                logger.debug("Duplikat übersprungen: %s – %s", company, title)
                return None
            job = Job(
                company=company.strip()[:255],
                title=title.strip()[:255],
                url=url.strip()[:1000],
                source=source,
                location=location.strip()[:255],
                description=description,
                remote=remote,
                status=JobStatus.NEW,
            )
            session.add(job)
            session.flush()
            return job.id

    # -------------------------------------------------------------- Lesen

    def get(self, job_id: int) -> Job | None:
        with session_scope(self._factory) as session:
            return session.get(Job, job_id)

    def jobs_with_status(self, status: JobStatus) -> list[Job]:
        with session_scope(self._factory) as session:
            rows = session.execute(
                select(Job).where(Job.status == status).order_by(Job.found_at.desc())
            ).scalars().all()
            return list(rows)

    def jobs_to_apply(self, min_score: int, limit: int) -> list[Job]:
        """Passende, noch nicht beworbene Stellen, beste Scores zuerst."""
        with session_scope(self._factory) as session:
            rows = session.execute(
                select(Job)
                .where(
                    Job.status == JobStatus.MATCHED,
                    Job.applied.is_(False),
                    Job.match_score >= min_score,
                )
                .order_by(Job.match_score.desc(), Job.found_at.desc())
                .limit(limit)
            ).scalars().all()
            return list(rows)

    def jobs_for_rescore(self) -> list[Job]:
        """Alle noch nicht beworbenen Jobs, deren Bewertung wiederholt werden kann."""
        with session_scope(self._factory) as session:
            rows = session.execute(
                select(Job)
                .where(
                    Job.applied.is_(False),
                    Job.status.in_([JobStatus.NEW, JobStatus.MATCHED, JobStatus.SKIPPED]),
                )
                .order_by(Job.found_at.desc())
            ).scalars().all()
            return list(rows)

    def list_jobs(self, criteria: JobFilter) -> list[Job]:
        with session_scope(self._factory) as session:
            query = select(Job)
            if criteria.status is not None:
                query = query.where(Job.status == criteria.status)
            if criteria.remote is not None:
                query = query.where(Job.remote.is_(criteria.remote))
            if criteria.applied is not None:
                query = query.where(Job.applied.is_(criteria.applied))
            if criteria.min_score is not None:
                query = query.where(Job.match_score >= criteria.min_score)
            if criteria.region == "germany":
                query = query.where(
                    or_(*[Job.location.ilike(f"%{term}%") for term in _GERMANY_TERMS])
                )
            elif criteria.region == "europe":
                query = query.where(
                    or_(
                        Job.remote.is_(True),
                        *[Job.location.ilike(f"%{term}%") for term in _EUROPE_TERMS],
                    )
                )
            if criteria.text:
                pattern = f"%{criteria.text}%"
                query = query.where(
                    or_(
                        Job.title.ilike(pattern),
                        Job.company.ilike(pattern),
                        Job.description.ilike(pattern),
                    )
                )
            query = query.order_by(Job.found_at.desc()).limit(criteria.limit).offset(criteria.offset)
            return list(session.execute(query).scalars().all())

    # --------------------------------------------------------- Aktualisieren

    def set_score(
        self,
        job_id: int,
        *,
        keyword_score: int,
        llm_score: int | None,
        match_score: int,
        language: str,
        min_match_score: int,
        force_skip: bool = False,
    ) -> None:
        """Speichert Scores und setzt den Status auf MATCHED oder SKIPPED."""
        with session_scope(self._factory) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.keyword_score = keyword_score
            job.llm_score = llm_score
            job.match_score = match_score
            job.language = language
            job.status = (
                JobStatus.SKIPPED
                if force_skip or match_score < min_match_score
                else JobStatus.MATCHED
            )

    def update_url(self, job_id: int, url: str) -> bool:
        """Ersetzt die Job-URL (z.B. LinkedIn → aufgelöstes Bewerbungsziel).

        Gibt False zurück, wenn die Ziel-URL bereits zu einer anderen Stelle
        gehört — der Aufrufer behandelt den Job dann als Duplikat.
        """
        with session_scope(self._factory) as session:
            existing = session.execute(
                select(Job.id).where(Job.url == url, Job.id != job_id)
            ).first()
            if existing is not None:
                return False
            job = session.get(Job, job_id)
            if job is None:
                return False
            job.url = url.strip()[:1000]
            return True

    def save_cover_letter(self, job_id: int, cover_letter: str) -> None:
        with session_scope(self._factory) as session:
            job = session.get(Job, job_id)
            if job is not None:
                job.cover_letter = cover_letter

    def mark_applied(self, job_id: int, screenshot_path: str | None = None) -> None:
        with session_scope(self._factory) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.applied = True
            job.applied_at = utcnow()
            job.status = JobStatus.APPLIED
            job.error = None
            if screenshot_path:
                job.screenshot_path = screenshot_path

    def mark_failed(self, job_id: int, error: str, screenshot_path: str | None = None) -> None:
        with session_scope(self._factory) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = JobStatus.FAILED
            job.error = error[:2000]
            if screenshot_path:
                job.screenshot_path = screenshot_path

    def set_error(self, job_id: int, error: str) -> None:
        """Fehlertext speichern, ohne den Status zu ändern (z.B. LLM offline)."""
        with session_scope(self._factory) as session:
            job = session.get(Job, job_id)
            if job is not None:
                job.error = error[:2000]

    def update_status(self, job_id: int, status: JobStatus) -> None:
        with session_scope(self._factory) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = status
            if status in (JobStatus.ANSWERED, JobStatus.INTERVIEW, JobStatus.REJECTED, JobStatus.OFFER):
                job.response_received = True
                job.response_at = utcnow()

    def record_attempt(
        self, job_id: int, *, success: bool, message: str, screenshot_path: str | None
    ) -> None:
        with session_scope(self._factory) as session:
            session.add(
                ApplicationAttempt(
                    job_id=job_id,
                    success=success,
                    message=message[:2000],
                    screenshot_path=screenshot_path,
                )
            )

    # ------------------------------------------------------------ Statistik

    def stats(self) -> dict[str, Any]:
        with session_scope(self._factory) as session:
            total = session.execute(select(func.count(Job.id))).scalar_one()
            by_status_rows = session.execute(
                select(Job.status, func.count(Job.id)).group_by(Job.status)
            ).all()
            by_source_rows = session.execute(
                select(Job.source, func.count(Job.id)).group_by(Job.source)
            ).all()
            applied = session.execute(
                select(func.count(Job.id)).where(Job.applied.is_(True))
            ).scalar_one()
            responses = session.execute(
                select(func.count(Job.id)).where(Job.response_received.is_(True))
            ).scalar_one()
            avg_score = session.execute(
                select(func.avg(Job.match_score)).where(Job.match_score.is_not(None))
            ).scalar_one()
            matched = session.execute(
                select(func.count(Job.id)).where(Job.status == JobStatus.MATCHED)
            ).scalar_one()
            return {
                "total": total,
                "matched": matched,
                "applied": applied,
                "responses": responses,
                "average_score": round(float(avg_score), 1) if avg_score is not None else None,
                "by_status": {status.value: count for status, count in by_status_rows},
                "by_source": {source: count for source, count in by_source_rows},
            }
