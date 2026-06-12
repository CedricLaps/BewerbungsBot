"""Generischer Scraper für Firmenkarriereseiten: sucht Links, deren Text zu den
Suchbegriffen passt. URLs werden in config.json unter 'company_pages' gepflegt."""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, JobPosting


class CompanyPagesScraper(BaseScraper):
    name = "company_pages"

    def search(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for page_url in self.config.company_pages:
            try:
                postings.extend(self._scrape_page(page_url))
            except requests.RequestException as exc:
                self.log.warning("Karriereseite %s nicht erreichbar: %s", page_url, exc)
            self.pause()
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _scrape_page(self, page_url: str) -> list[JobPosting]:
        response = self.session.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        company = urlparse(page_url).netloc.removeprefix("www.")
        seen: set[str] = set()
        results: list[JobPosting] = []
        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            if not title or len(title) > 120 or not self.matches(title):
                continue
            url = urljoin(page_url, str(anchor["href"]))
            if url in seen or url.rstrip("/") == page_url.rstrip("/"):
                continue
            seen.add(url)
            results.append(
                JobPosting(
                    title=title,
                    company=company,
                    url=url,
                    source=self.name,
                )
            )
        return results
