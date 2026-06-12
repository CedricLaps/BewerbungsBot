"""Bewerbungs-Manager: wählt Applier, erzeugt Anschreiben und verbucht Ergebnisse."""
from __future__ import annotations

import logging
import time

from apply.base import ApplicationResult, BaseApplier
from apply.greenhouse import GreenhouseApplier
from apply.lever import LeverApplier
from apply.personio import PersonioApplier
from apply.workday import WorkdayApplier
from backend.config import AppConfig
from backend.llm_client import LLMClient, LLMError, LLMUnavailableError
from database.models import Job, JobStatus
from database.repository import JobRepository
from scrapers.base import clean_url
from scrapers.linkedin import resolve_apply_target

logger = logging.getLogger(__name__)

# Obergrenze der pro Lauf verarbeiteten Stellen (Anschreiben/Auflösung);
# die Zahl echter Absendungen begrenzt max_applications_per_run separat.
_PROCESS_LIMIT = 500


class ApplyManager:
    """Verarbeitet passende Jobs: Anschreiben generieren, Formular ausfüllen, absenden."""

    def __init__(self, config: AppConfig, repository: JobRepository, llm: LLMClient) -> None:
        self.config = config
        self.repository = repository
        self.llm = llm
        self.appliers: list[BaseApplier] = [
            GreenhouseApplier(config),
            LeverApplier(config),
            PersonioApplier(config),
            WorkdayApplier(config),
        ]

    def find_applier(self, url: str) -> BaseApplier | None:
        for applier in self.appliers:
            if applier.can_handle(url):
                return applier
        return None

    def _resolve_linkedin_target(self, job: Job) -> str:
        """Löst das Bewerbungsziel hinter einer LinkedIn-Anzeige auf.

        Rückgabe: 'resolved' (URL ersetzt), 'duplicate' (Ziel gehört zu anderer
        Stelle, Job aussortiert) oder 'unresolved' (kein externes Ziel gefunden).
        """
        if job.id is None:
            return "unresolved"
        resolved = resolve_apply_target(job.url)
        time.sleep(self.config.request_delay_seconds)
        if not resolved:
            return "unresolved"
        cleaned = clean_url(resolved)
        if "linkedin." in cleaned.lower():
            # Easy-Apply oder Login-Mauer — kein nutzbares externes Ziel
            return "unresolved"
        if not self.repository.update_url(job.id, cleaned):
            logger.info(
                "Bewerbungsziel von %s — %s gehört zu bereits erfasster Stelle, "
                "als Duplikat aussortiert", job.company, job.title,
            )
            self.repository.update_status(job.id, JobStatus.SKIPPED)
            self.repository.set_error(
                job.id, "Duplikat: Bewerbungsziel ist bereits unter einer anderen Stelle erfasst"
            )
            return "duplicate"
        job.url = cleaned
        logger.info(
            "Bewerbungsziel aufgelöst: %s — %s → %s", job.company, job.title, cleaned
        )
        return "resolved"

    def run(self, limit: int | None = None) -> dict[str, int]:
        """Verarbeitet alle passenden Stellen: Anschreiben für jede, Auflösung von
        LinkedIn-Zielen, und bis zu `limit` echte Absendungen (Rest wird vertagt)."""
        max_submissions = limit if limit is not None else self.config.max_applications_per_run
        jobs = self.repository.jobs_to_apply(self.config.min_match_score, _PROCESS_LIMIT)
        counters = {
            "processed": 0, "submitted": 0, "deferred": 0, "failed": 0,
            "no_applier": 0, "no_letter": 0, "duplicate": 0,
        }
        for job in jobs:
            counters["processed"] += 1
            outcome = self.apply_to_job(
                job, allow_submit=counters["submitted"] < max_submissions
            )
            counters[outcome] += 1
        logger.info("Bewerbungslauf abgeschlossen: %s", counters)
        return counters

    def apply_to_job(self, job: Job, allow_submit: bool = True) -> str:
        """Bewirbt sich auf eine Stelle; gibt den Zähler-Schlüssel des Ergebnisses zurück.

        Das Anschreiben wird immer zuerst generiert — auch wenn keine automatische
        Bewerbung möglich ist, liegt es dann für die manuelle Bewerbung bereit.
        Bei LinkedIn-URLs wird das externe Bewerbungsziel aufgelöst; zeigt es auf
        ein unterstütztes ATS, läuft die Bewerbung automatisch weiter.
        """
        if job.id is None:
            return "failed"

        cover_letter = job.cover_letter
        if not cover_letter:
            try:
                cover_letter = self.llm.generate_cover_letter(
                    job.title, job.company, job.description
                )
                self.repository.save_cover_letter(job.id, cover_letter)
            except LLMUnavailableError as exc:
                logger.warning("LLM offline, Job %s bleibt offen: %s", job.id, exc)
                self.repository.set_error(job.id, f"Anschreiben fehlt, LLM offline: {exc}")
                return "no_letter"
            except LLMError as exc:
                logger.warning("Anschreiben für Job %s fehlgeschlagen: %s", job.id, exc)
                self.repository.set_error(job.id, f"Anschreiben-Generierung fehlgeschlagen: {exc}")
                return "no_letter"

        applier = self.find_applier(job.url)
        if applier is None and "linkedin.com/jobs" in job.url.lower():
            resolution = self._resolve_linkedin_target(job)
            if resolution == "duplicate":
                return "duplicate"
            if resolution == "resolved":
                applier = self.find_applier(job.url)

        if applier is None:
            logger.info(
                "Kein Applier für %s (%s) — Anschreiben liegt bereit, manuelle Bewerbung nötig",
                job.url, job.company,
            )
            self.repository.update_status(job.id, JobStatus.MANUAL)
            self.repository.set_error(
                job.id,
                "Keine automatische Bewerbung für diese Plattform möglich — "
                "das Anschreiben liegt in den Details zum Kopieren bereit",
            )
            return "no_applier"

        if not allow_submit:
            logger.info(
                "Limit erreicht — %s (%s) wird im nächsten Lauf beworben",
                job.title, job.company,
            )
            return "deferred"

        logger.info("Bewerbe mich: %s — %s (%s)", job.company, job.title, applier.name)
        assert cover_letter is not None
        result: ApplicationResult = applier.apply(job, cover_letter)
        self.repository.record_attempt(
            job.id,
            success=result.submitted,
            message=result.message,
            screenshot_path=result.screenshot_path,
        )
        if result.submitted:
            self.repository.mark_applied(job.id, result.screenshot_path)
            logger.info("Bewerbung gesendet: %s — %s", job.company, job.title)
            return "submitted"
        self.repository.mark_failed(job.id, result.message, result.screenshot_path)
        logger.warning("Bewerbung gescheitert (%s): %s", job.company, result.message)
        return "failed"
