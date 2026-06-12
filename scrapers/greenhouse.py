"""Greenhouse-Scraper über die öffentliche Boards-API (keine Anmeldung nötig)."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, JobPosting

_API_URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


class GreenhouseScraper(BaseScraper):
    name = "greenhouse"

    def search(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for board in self.config.greenhouse_boards:
            try:
                postings.extend(self._fetch_board(board))
            except requests.RequestException as exc:
                self.log.warning("Board %s nicht erreichbar: %s", board, exc)
            self.pause()
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _fetch_board(self, board: str) -> list[JobPosting]:
        response = self.session.get(_API_URL.format(board=board), timeout=30)
        if response.status_code == 404:
            self.log.warning("Greenhouse-Board %s existiert nicht (404)", board)
            return []
        response.raise_for_status()
        payload = response.json()
        results: list[JobPosting] = []
        for job in payload.get("jobs", []):
            title = str(job.get("title", ""))
            if not title or not self.matches(title):
                continue
            content_html = str(job.get("content", ""))
            description = BeautifulSoup(content_html, "html.parser").get_text(" ", strip=True)
            location = str((job.get("location") or {}).get("name", ""))
            results.append(
                JobPosting(
                    title=title,
                    company=str(job.get("company_name") or board),
                    url=str(job.get("absolute_url", "")),
                    source=self.name,
                    location=location,
                    description=description,
                )
            )
        return results
