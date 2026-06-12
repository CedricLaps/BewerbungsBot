"""Personio-Scraper über den öffentlichen XML-Stellenfeed."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, JobPosting

_FEED_URL = "https://{company}.jobs.personio.de/xml"
_JOB_URL = "https://{company}.jobs.personio.de/job/{job_id}"


class PersonioScraper(BaseScraper):
    name = "personio"

    def search(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for company in self.config.personio_companies:
            try:
                postings.extend(self._fetch_company(company))
            except (requests.RequestException, ET.ParseError) as exc:
                self.log.warning("Personio-Feed %s nicht lesbar: %s", company, exc)
            self.pause()
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _fetch_company(self, company: str) -> list[JobPosting]:
        response = self.session.get(_FEED_URL.format(company=company), timeout=30)
        if response.status_code == 404:
            self.log.warning("Personio-Feed %s existiert nicht (404)", company)
            return []
        response.raise_for_status()
        root = ET.fromstring(response.content)
        results: list[JobPosting] = []
        for position in root.iter("position"):
            title = (position.findtext("name") or "").strip()
            job_id = (position.findtext("id") or "").strip()
            if not title or not job_id or not self.matches(title):
                continue
            office = (position.findtext("office") or "").strip()
            schedule = (position.findtext("schedule") or "").strip()
            description_parts: list[str] = []
            for value in position.iter("value"):
                html = value.text or ""
                description_parts.append(
                    BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
                )
            results.append(
                JobPosting(
                    title=title,
                    company=company,
                    url=_JOB_URL.format(company=company, job_id=job_id),
                    source=self.name,
                    location=office,
                    description=" ".join(part for part in description_parts if part),
                    remote="remote" in f"{office} {schedule}".lower(),
                )
            )
        return results
