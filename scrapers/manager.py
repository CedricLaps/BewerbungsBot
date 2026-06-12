"""Führt alle aktivierten Scraper aus und dedupliziert die Ergebnisse."""
from __future__ import annotations

import logging

from backend.config import AppConfig
from scrapers.base import BaseScraper, JobPosting
from scrapers.company_pages import CompanyPagesScraper
from scrapers.greenhouse import GreenhouseScraper
from scrapers.indeed import IndeedScraper
from scrapers.lever import LeverScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.personio import PersonioScraper
from scrapers.stepstone import StepstoneScraper
from scrapers.workday import WorkdayScraper

logger = logging.getLogger(__name__)

_SCRAPER_CLASSES: dict[str, type[BaseScraper]] = {
    "linkedin": LinkedInScraper,
    "stepstone": StepstoneScraper,
    "indeed": IndeedScraper,
    "greenhouse": GreenhouseScraper,
    "lever": LeverScraper,
    "personio": PersonioScraper,
    "workday": WorkdayScraper,
    "company_pages": CompanyPagesScraper,
}


class ScraperManager:
    """Erzeugt die konfigurierten Scraper und sammelt deren Ergebnisse robust ein."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.scrapers: list[BaseScraper] = []
        for name in config.enabled_scrapers:
            scraper_class = _SCRAPER_CLASSES.get(name)
            if scraper_class is None:
                logger.warning("Unbekannter Scraper in Konfiguration: %s", name)
                continue
            self.scrapers.append(scraper_class(config))

    def run_all(self) -> list[JobPosting]:
        """Führt alle Scraper aus; ein Fehler in einer Quelle stoppt die anderen nicht."""
        collected: list[JobPosting] = []
        for scraper in self.scrapers:
            logger.info("Starte Scraper: %s", scraper.name)
            try:
                collected.extend(scraper.search())
            except Exception:
                logger.exception("Scraper %s ist fehlgeschlagen", scraper.name)
        return self._deduplicate(collected)

    @staticmethod
    def _deduplicate(postings: list[JobPosting]) -> list[JobPosting]:
        seen_urls: set[str] = set()
        seen_identity: set[tuple[str, str, str]] = set()
        unique: list[JobPosting] = []
        for posting in postings:
            identity = (
                posting.company.lower(),
                posting.title.lower(),
                posting.location.lower(),
            )
            if posting.url in seen_urls or identity in seen_identity:
                continue
            seen_urls.add(posting.url)
            seen_identity.add(identity)
            unique.append(posting)
        logger.info("%d eindeutige Stellen nach Deduplizierung", len(unique))
        return unique
