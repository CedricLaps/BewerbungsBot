"""Workday-Scraper über die öffentliche CXS-Such-API der jeweiligen Karriereseite."""
from __future__ import annotations

import requests

from backend.config import WorkdaySite
from scrapers.base import BaseScraper, JobPosting

_SEARCH_URL = "https://{host}/wday/cxs/{tenant}/{site}/jobs"
_PAGE_SIZE = 20


class WorkdayScraper(BaseScraper):
    name = "workday"

    def search(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for site in self.config.workday_sites:
            for keyword in self.config.search_keywords:
                try:
                    postings.extend(self._search_site(site, keyword))
                except requests.RequestException as exc:
                    self.log.warning("Workday %s (%s): %s", site.host, keyword, exc)
                self.pause()
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _search_site(self, site: WorkdaySite, keyword: str) -> list[JobPosting]:
        url = _SEARCH_URL.format(host=site.host, tenant=site.tenant, site=site.site)
        response = self.session.post(
            url,
            json={
                "appliedFacets": {},
                "limit": _PAGE_SIZE,
                "offset": 0,
                "searchText": keyword,
            },
            timeout=30,
        )
        if response.status_code == 404:
            self.log.warning("Workday-Site %s/%s existiert nicht (404)", site.host, site.site)
            return []
        response.raise_for_status()
        payload = response.json()
        results: list[JobPosting] = []
        for job in payload.get("jobPostings", []):
            title = str(job.get("title", ""))
            external_path = str(job.get("externalPath", ""))
            if not title or not external_path or not self.matches(title):
                continue
            results.append(
                JobPosting(
                    title=title,
                    company=site.company or site.tenant,
                    url=f"https://{site.host}/{site.site}{external_path}",
                    source=self.name,
                    location=str(job.get("locationsText", "")),
                )
            )
        return results
