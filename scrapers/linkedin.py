"""LinkedIn-Scraper über die öffentliche Gast-Suche (ohne Login).

Hinweis: LinkedIn drosselt aggressiv. Der Scraper hält Pausen ein, begrenzt die
Seitenzahl und bricht bei HTTP 429 sauber ab.
"""
from __future__ import annotations

import html
import re

import requests
from bs4 import BeautifulSoup, Tag

from backend.ats import is_supported_ats
from scrapers.base import BaseScraper, JobPosting, clean_url

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
_PAGE_SIZE = 25
_JOB_ID_RE = re.compile(r"(\d{6,})")
# Externes Bewerbungsziel in der Gast-Detailseite: <code id="applyUrl"><!--"https://…"--></code>
_APPLY_URL_RE = re.compile(r'id="applyUrl"[^>]*>\s*(?:<!--)?\s*"?(https?://[^"<\s]+)')


def extract_apply_url(html_text: str) -> str | None:
    """Liest das externe Bewerbungsziel aus der LinkedIn-Gast-Detailseite."""
    match = _APPLY_URL_RE.search(html_text)
    if match is None:
        return None
    return html.unescape(match.group(1))


def follow_redirects(session: requests.Session, url: str, timeout: int = 20) -> str | None:
    """Folgt Tracking-Weiterleitungen (z.B. appcast.io) bis zur endgültigen Ziel-URL."""
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
        final_url = str(response.url)
        response.close()
        return final_url
    except requests.RequestException:
        return None


def resolve_apply_target(job_url: str, session: requests.Session | None = None) -> str | None:
    """Löst das externe Bewerbungsziel einer LinkedIn-Stellen-URL auf.

    Holt die Gast-Detailseite, extrahiert das applyUrl-Ziel und folgt allen
    Weiterleitungen. Gibt None zurück, wenn kein externes Ziel existiert
    (z.B. reine LinkedIn-Easy-Apply-Anzeigen) oder LinkedIn drosselt.
    """
    job_id_match = _JOB_ID_RE.search(job_url)
    if job_id_match is None:
        return None
    if session is None:
        from scrapers.base import USER_AGENT

        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        })
    try:
        detail = session.get(_DETAIL_URL.format(job_id=job_id_match.group(1)), timeout=20)
    except requests.RequestException:
        return None
    if detail.status_code != 200:
        return None
    apply_url = extract_apply_url(detail.text)
    if apply_url is None:
        return None
    return follow_redirects(session, apply_url)

# Abbildung der konfigurierten Standorte auf LinkedIn-Suchparameter
_LOCATION_PARAMS: dict[str, dict[str, str]] = {
    "deutschland": {"location": "Germany"},
    "remote": {"location": "Germany", "f_WT": "2"},
    "europa remote": {"location": "European Union", "f_WT": "2"},
}


class LinkedInScraper(BaseScraper):
    name = "linkedin"

    def search(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        throttled = False
        for keyword in self.config.search_keywords:
            if throttled:
                break
            for location in self.config.locations:
                params = dict(
                    _LOCATION_PARAMS.get(location.lower(), {"location": location})
                )
                params.update({"keywords": keyword, "f_TPR": "r604800"})
                for page in range(self.config.max_pages_per_search):
                    params["start"] = str(page * _PAGE_SIZE)
                    try:
                        page_postings, status = self._fetch_page(params)
                    except requests.RequestException as exc:
                        self.log.warning("Suche '%s' (%s): %s", keyword, location, exc)
                        break
                    if status == 429:
                        self.log.warning("LinkedIn drosselt (429) — Suche wird beendet")
                        throttled = True
                        break
                    postings.extend(page_postings)
                    self.pause()
                if throttled:
                    break
        self._enrich_descriptions(postings)
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _fetch_page(self, params: dict[str, str]) -> tuple[list[JobPosting], int]:
        response = self.session.get(_SEARCH_URL, params=params, timeout=30)
        if response.status_code != 200:
            return [], response.status_code
        soup = BeautifulSoup(response.text, "html.parser")
        results: list[JobPosting] = []
        for card in soup.select("div.base-card, li > div.base-search-card"):
            posting = self._parse_card(card)
            if posting is not None and self.matches(posting.title):
                results.append(posting)
        return results, response.status_code

    def _parse_card(self, card: Tag) -> JobPosting | None:
        title_node = card.select_one("h3.base-search-card__title")
        company_node = card.select_one("h4.base-search-card__subtitle")
        link_node = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if title_node is None or link_node is None:
            return None
        location_node = card.select_one("span.job-search-card__location")
        return JobPosting(
            title=title_node.get_text(strip=True),
            company=company_node.get_text(strip=True) if company_node else "",
            url=str(link_node.get("href", "")),
            source=self.name,
            location=location_node.get_text(strip=True) if location_node else "",
        )

    def _enrich_descriptions(self, postings: list[JobPosting]) -> None:
        """Lädt für die ersten N Treffer die Beschreibung über die Gast-Detail-API nach."""
        for posting in postings[: self.config.max_descriptions_per_run]:
            job_id_match = _JOB_ID_RE.search(posting.url)
            if job_id_match is None:
                continue
            try:
                response = self.session.get(
                    _DETAIL_URL.format(job_id=job_id_match.group(1)), timeout=30
                )
            except requests.RequestException as exc:
                self.log.debug("Detailseite %s: %s", posting.url, exc)
                continue
            if response.status_code != 200:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            body = soup.select_one("div.show-more-less-html__markup")
            if body is not None:
                posting.description = body.get_text(" ", strip=True)
            self._resolve_ats_target(posting, response.text)
            self.pause()

    def _resolve_ats_target(self, posting: JobPosting, detail_html: str) -> None:
        """Ersetzt die LinkedIn-URL durch das Bewerbungsziel, wenn es auf ein
        unterstütztes ATS (Greenhouse/Lever/Personio/Workday) zeigt — dann kann
        der Bot sich automatisch bewerben statt nur zu verlinken."""
        apply_url = extract_apply_url(detail_html)
        if apply_url is None:
            return
        final_url = follow_redirects(self.session, apply_url)
        if final_url is None:
            self.log.debug("Bewerbungsziel nicht auflösbar: %s", apply_url)
            return
        if is_supported_ats(final_url):
            posting.url = clean_url(final_url)
            self.log.info(
                "Bewerbungsziel aufgelöst: %s — %s → %s",
                posting.company, posting.title, posting.url,
            )
