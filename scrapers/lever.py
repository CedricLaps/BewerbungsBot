"""Lever-Scraper über die öffentliche Postings-API (keine Anmeldung nötig)."""
from __future__ import annotations

import requests

from scrapers.base import BaseScraper, JobPosting

_API_URL = "https://api.lever.co/v0/postings/{company}?mode=json"


class LeverScraper(BaseScraper):
    name = "lever"

    def search(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for company in self.config.lever_companies:
            try:
                postings.extend(self._fetch_company(company))
            except requests.RequestException as exc:
                self.log.warning("Lever-Account %s nicht erreichbar: %s", company, exc)
            self.pause()
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _fetch_company(self, company: str) -> list[JobPosting]:
        response = self.session.get(_API_URL.format(company=company), timeout=30)
        if response.status_code == 404:
            self.log.warning("Lever-Account %s existiert nicht (404)", company)
            return []
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        results: list[JobPosting] = []
        for job in payload:
            title = str(job.get("text", ""))
            if not title or not self.matches(title):
                continue
            categories = job.get("categories") or {}
            workplace = str(job.get("workplaceType", "")).lower()
            results.append(
                JobPosting(
                    title=title,
                    company=company,
                    url=str(job.get("hostedUrl", "")),
                    source=self.name,
                    location=str(categories.get("location", "")),
                    description=str(job.get("descriptionPlain", "")),
                    remote=workplace == "remote",
                )
            )
        return results
