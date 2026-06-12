"""Indeed-Scraper mit Playwright. Indeed nutzt Cloudflare-Bot-Schutz; Blockaden
werden erkannt, geloggt und führen zu einem sauberen Abbruch statt zu Fehlern."""
from __future__ import annotations

from urllib.parse import urlencode

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from scrapers.base import USER_AGENT, BaseScraper, JobPosting

_BASE_URL = "https://de.indeed.com"
_CARD_SELECTOR = "div.job_seen_beacon"
_BLOCK_MARKERS = ("verify you are human", "cloudflare", "challenge-platform")

# Indeed-Suchorte je konfiguriertem Standort
_LOCATION_QUERY: dict[str, str] = {
    "deutschland": "Deutschland",
    "remote": "Homeoffice",
    "europa remote": "Remote",
}


class IndeedScraper(BaseScraper):
    name = "indeed"

    def search(self) -> list[JobPosting]:
        postings: list[JobPosting] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.config.headless)
                context = browser.new_context(user_agent=USER_AGENT, locale="de-DE")
                page = context.new_page()
                page.set_default_timeout(20_000)
                try:
                    for keyword in self.config.search_keywords:
                        for location in self.config.locations:
                            blocked = self._search_one(page, keyword, location, postings)
                            if blocked:
                                self.log.warning(
                                    "Indeed blockiert automatisierte Zugriffe — Suche beendet"
                                )
                                self.log.info("%d passende Stellen gefunden", len(postings))
                                return postings
                finally:
                    context.close()
                    browser.close()
        except PlaywrightError as exc:
            self.log.error("Playwright-Fehler: %s", exc)
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _search_one(
        self, page: Page, keyword: str, location: str, postings: list[JobPosting]
    ) -> bool:
        """Sucht eine Kombination; gibt True zurück, wenn Indeed blockiert."""
        query = urlencode({
            "q": keyword,
            "l": _LOCATION_QUERY.get(location.lower(), location),
            "fromage": "7",
        })
        try:
            page.goto(f"{_BASE_URL}/jobs?{query}", wait_until="domcontentloaded")
            content = page.content().lower()
            if any(marker in content for marker in _BLOCK_MARKERS):
                return True
            page.wait_for_selector(_CARD_SELECTOR, timeout=10_000)
        except PlaywrightError as exc:
            self.log.warning("Suche '%s' (%s): %s", keyword, location, exc)
            return False
        for card in page.locator(_CARD_SELECTOR).all():
            try:
                link = card.locator("h2.jobTitle a").first
                title = link.inner_text(timeout=3000).strip()
                href = link.get_attribute("href", timeout=3000) or ""
                if not title or not href or not self.matches(title):
                    continue
                company = self._safe_text(card, "[data-testid='company-name']")
                job_location = self._safe_text(card, "[data-testid='text-location']")
                postings.append(
                    JobPosting(
                        title=title,
                        company=company,
                        url=f"{_BASE_URL}{href}" if href.startswith("/") else href,
                        source=self.name,
                        location=job_location,
                    )
                )
            except PlaywrightError:
                continue
        self.pause()
        return False

    @staticmethod
    def _safe_text(card: object, selector: str) -> str:
        try:
            return card.locator(selector).first.inner_text(timeout=2000).strip()  # type: ignore[attr-defined]
        except PlaywrightError:
            return ""
