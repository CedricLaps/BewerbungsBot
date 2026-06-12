"""StepStone-Scraper mit Playwright (die Seite ist stark JavaScript-basiert)."""
from __future__ import annotations

from urllib.parse import quote

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from scrapers.base import USER_AGENT, BaseScraper, JobPosting

_SEARCH_URL = "https://www.stepstone.de/jobs/{keyword}/in-deutschland"
_COOKIE_SELECTORS = (
    "#ccmgt_explicit_accept",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Accept all')",
)
_CARD_SELECTOR = "article[data-testid='job-item'], article[data-at='job-item']"


class StepstoneScraper(BaseScraper):
    name = "stepstone"

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
                        postings.extend(self._search_keyword(page, keyword))
                finally:
                    context.close()
                    browser.close()
        except PlaywrightError as exc:
            self.log.error("Playwright-Fehler: %s", exc)
        self.log.info("%d passende Stellen gefunden", len(postings))
        return postings

    def _search_keyword(self, page: Page, keyword: str) -> list[JobPosting]:
        results: list[JobPosting] = []
        try:
            page.goto(_SEARCH_URL.format(keyword=quote(keyword)), wait_until="domcontentloaded")
            self._accept_cookies(page)
            page.wait_for_selector(_CARD_SELECTOR, timeout=15_000)
        except PlaywrightError as exc:
            self.log.warning("Suche '%s' lieferte keine Ergebnisliste: %s", keyword, exc)
            return results
        for card in page.locator(_CARD_SELECTOR).all():
            try:
                title_node = card.locator(
                    "a[data-testid='job-item-title'], a[data-at='job-item-title']"
                ).first
                title = title_node.inner_text(timeout=3000).strip()
                href = title_node.get_attribute("href", timeout=3000) or ""
                if not title or not href or not self.matches(title):
                    continue
                company = self._safe_text(
                    card, "span[data-at='job-item-company-name'], [data-testid='job-item-company-name']"
                )
                location = self._safe_text(
                    card, "span[data-at='job-item-location'], [data-testid='job-item-location']"
                )
                if href.startswith("/"):
                    href = f"https://www.stepstone.de{href}"
                results.append(
                    JobPosting(
                        title=title,
                        company=company,
                        url=href,
                        source=self.name,
                        location=location,
                    )
                )
            except PlaywrightError:
                continue
        self.pause()
        return results

    @staticmethod
    def _safe_text(card: object, selector: str) -> str:
        try:
            return card.locator(selector).first.inner_text(timeout=2000).strip()  # type: ignore[attr-defined]
        except PlaywrightError:
            return ""

    @staticmethod
    def _accept_cookies(page: Page) -> None:
        for selector in _COOKIE_SELECTORS:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=2000):
                    button.click(timeout=3000)
                    return
            except PlaywrightError:
                continue
