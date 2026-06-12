"""Pipeline: verbindet Scraper, Matching, LLM und Bewerbungs-Manager."""
from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session, sessionmaker

from apply.manager import ApplyManager
from backend.config import AppConfig
from backend.language import detect_language
from backend.llm_client import LLMClient, LLMError
from backend.matching import combined_score, keyword_score, location_allowed, title_blocked
from database.models import JobStatus
from database.repository import JobRepository
from scrapers.manager import ScraperManager

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestriert die drei Phasen: Sammeln, Bewerten, Bewerben."""

    def __init__(self, config: AppConfig, session_factory: sessionmaker[Session]) -> None:
        self.config = config
        self.repository = JobRepository(session_factory)
        self.llm = LLMClient(config)
        self.apply_manager = ApplyManager(config, self.repository, self.llm)
        # Scrape- und Apply-Läufe nicht parallel zu sich selbst ausführen
        self._scrape_lock = threading.Lock()
        self._apply_lock = threading.Lock()

    # ------------------------------------------------------------- Sammeln

    def scrape_and_score(self) -> dict[str, int]:
        """Sammelt Stellen aus allen Quellen, speichert Neue und bewertet sie."""
        if not self._scrape_lock.acquire(blocking=False):
            logger.info("Scrape-Lauf läuft bereits — übersprungen")
            return {
                "found": 0, "new": 0, "location_filtered": 0,
                "matched": 0, "skipped": 0, "blocked": 0,
            }
        try:
            postings = ScraperManager(self.config).run_all()
            new_count = 0
            filtered_count = 0
            for posting in postings:
                if self.config.germany_or_remote_only and not location_allowed(
                    posting.location, posting.remote
                ):
                    filtered_count += 1
                    continue
                job_id = self.repository.add_job(
                    company=posting.company or "Unbekannt",
                    title=posting.title,
                    url=posting.url,
                    source=posting.source,
                    location=posting.location,
                    description=posting.description,
                    remote=posting.remote,
                )
                if job_id is not None:
                    new_count += 1
            scored = self.score_new_jobs()
            result = {
                "found": len(postings),
                "new": new_count,
                "location_filtered": filtered_count,
                **scored,
            }
            logger.info("Scrape-Lauf abgeschlossen: %s", result)
            return result
        finally:
            self._scrape_lock.release()

    # ------------------------------------------------------------ Bewerten

    def score_new_jobs(self) -> dict[str, int]:
        """Bewertet alle Jobs mit Status NEW (Keyword-Score + optional LLM-Score)."""
        return self._score_jobs(self.repository.jobs_with_status(JobStatus.NEW))

    def rescore_unapplied(self) -> dict[str, int]:
        """Bewertet alle noch nicht beworbenen Jobs neu (z.B. nach Keyword-Änderungen)."""
        return self._score_jobs(self.repository.jobs_for_rescore())

    def _score_jobs(self, jobs: list) -> dict[str, int]:
        llm_available = self.llm.is_available()
        if not llm_available:
            logger.warning("Ollama nicht erreichbar — Scoring nur über Keywords")
        matched = 0
        skipped = 0
        blocked_count = 0
        for job in jobs:
            if job.id is None:
                continue
            blocked = title_blocked(job.title, self.config.title_blocklist) or (
                self.config.germany_or_remote_only
                and not location_allowed(job.location, job.remote)
            )
            text = f"{job.title}\n{job.description}"
            kw_score = keyword_score(
                text, self.config.positive_keywords, self.config.negative_keywords
            )
            llm_score: int | None = None
            # Gesperrte Titel brauchen keinen (teuren) LLM-Score
            if not blocked and llm_available and job.description:
                try:
                    llm_score = self.llm.calculate_match_score(job.title, job.description)
                except LLMError as exc:
                    logger.warning("LLM-Score für Job %s fehlgeschlagen: %s", job.id, exc)
            total = combined_score(kw_score, llm_score)
            language = detect_language(text)
            self.repository.set_score(
                job.id,
                keyword_score=kw_score,
                llm_score=llm_score,
                match_score=total,
                language=language,
                min_match_score=self.config.min_match_score,
                force_skip=blocked,
            )
            if blocked:
                blocked_count += 1
                skipped += 1
            elif total >= self.config.min_match_score:
                matched += 1
            else:
                skipped += 1
        logger.info(
            "Scoring: %d passend, %d unter Schwelle (davon %d per Titel-Sperrliste)",
            matched, skipped, blocked_count,
        )
        return {"matched": matched, "skipped": skipped, "blocked": blocked_count}

    # ------------------------------------------------------------ Bewerben

    def apply_pending(self, limit: int | None = None) -> dict[str, int]:
        """Bewirbt sich auf alle passenden, noch offenen Stellen."""
        if not self._apply_lock.acquire(blocking=False):
            logger.info("Bewerbungslauf läuft bereits — übersprungen")
            return {
                "processed": 0, "submitted": 0, "deferred": 0, "failed": 0,
                "no_applier": 0, "no_letter": 0, "duplicate": 0,
            }
        try:
            return self.apply_manager.run(limit)
        finally:
            self._apply_lock.release()

    def apply_single(self, job_id: int) -> str:
        """Bewirbt sich gezielt auf eine Stelle (Dashboard-Aktion)."""
        job = self.repository.get(job_id)
        if job is None:
            return "not_found"
        if job.applied:
            return "already_applied"
        return self.apply_manager.apply_to_job(job)
