"""Basisklasse für Applier: Browser-Lifecycle, Formular-Helfer, Screenshots, Fehlerbilder."""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from backend.config import AppConfig
from database.models import Job

_COOKIE_SELECTORS: tuple[str, ...] = (
    "#onetrust-accept-btn-handler",
    "[data-testid='uc-accept-all-button']",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Akzeptieren')",
)

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


class ApplyError(RuntimeError):
    """Bewerbungsformular konnte nicht ausgefüllt oder abgesendet werden."""


@dataclass(frozen=True)
class ApplicationResult:
    """Ergebnis eines Bewerbungsversuchs."""

    success: bool
    submitted: bool
    message: str
    screenshot_path: str | None = None


class BaseApplier(ABC):
    """Gemeinsamer Ablauf: Seite öffnen, Cookies wegklicken, Formular füllen, absenden."""

    name: str = "base"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.log = logging.getLogger(f"apply.{self.name}")

    # ------------------------------------------------------------ Vertrag

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Ob dieser Applier die angegebene Bewerbungs-URL bedienen kann."""

    @abstractmethod
    def fill_form(self, page: Page, job: Job, cover_letter: str) -> None:
        """Füllt das Formular aus; wirft ApplyError bei Problemen."""

    def submit_selectors(self) -> tuple[str, ...]:
        return (
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('Absenden')",
            "button:has-text('Bewerben')",
        )

    def context_options(self) -> dict[str, object]:
        """Zusätzliche Browser-Kontext-Optionen (z.B. storage_state bei Workday)."""
        return {"locale": "de-DE"}

    # ------------------------------------------------------------- Ablauf

    def apply(self, job: Job, cover_letter: str) -> ApplicationResult:
        cv = Path(self.config.cv_path)
        if not cv.is_file():
            return ApplicationResult(
                success=False,
                submitted=False,
                message=f"Lebenslauf nicht gefunden: {cv}",
            )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.config.headless)
                context = browser.new_context(**self.context_options())  # type: ignore[arg-type]
                page = context.new_page()
                page.set_default_timeout(25_000)
                try:
                    return self._run(page, job, cover_letter)
                finally:
                    context.close()
                    browser.close()
        except PlaywrightError as exc:
            self.log.error("Browser-Fehler bei Job %s: %s", job.id, exc)
            return ApplicationResult(
                success=False, submitted=False, message=f"Browser-Fehler: {exc}"
            )

    def _run(self, page: Page, job: Job, cover_letter: str) -> ApplicationResult:
        try:
            page.goto(job.url, wait_until="domcontentloaded")
            self.dismiss_cookie_banner(page)
            self.fill_form(page, job, cover_letter)
            if not self.config.auto_submit:
                shot = self.screenshot(page, job, "filled")
                return ApplicationResult(
                    success=False,
                    submitted=False,
                    message="Formular ausgefüllt, aber auto_submit ist deaktiviert",
                    screenshot_path=shot,
                )
            self.submit(page)
            page.wait_for_timeout(3000)
            shot = self.screenshot(page, job, "submitted")
            return ApplicationResult(
                success=True,
                submitted=True,
                message="Bewerbung abgesendet",
                screenshot_path=shot,
            )
        except (ApplyError, PlaywrightError) as exc:
            shot = self.screenshot(page, job, "error")
            self.log.error("Bewerbung für Job %s fehlgeschlagen: %s", job.id, exc)
            return ApplicationResult(
                success=False,
                submitted=False,
                message=f"{type(exc).__name__}: {exc}",
                screenshot_path=shot,
            )

    def submit(self, page: Page) -> None:
        if not self.click_first(page, self.submit_selectors()):
            raise ApplyError("Kein Submit-Button gefunden")

    # -------------------------------------------------------------- Helfer

    def screenshot(self, page: Page, job: Job, suffix: str) -> str | None:
        directory = Path(self.config.logs_dir) / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        company = _FILENAME_SAFE_RE.sub("-", job.company)[:40] or "unbekannt"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = directory / f"{job.id}_{company}_{suffix}_{timestamp}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            return str(path)
        except PlaywrightError as exc:
            self.log.warning("Screenshot fehlgeschlagen: %s", exc)
            return None

    @staticmethod
    def dismiss_cookie_banner(page: Page) -> None:
        for selector in _COOKIE_SELECTORS:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=1500):
                    button.click(timeout=3000)
                    return
            except PlaywrightError:
                continue

    @staticmethod
    def fill_first(page: Page, selectors: tuple[str, ...], value: str) -> bool:
        """Füllt das erste sichtbare Feld aus der Selektorliste."""
        for selector in selectors:
            try:
                field = page.locator(selector).first
                if field.is_visible(timeout=1500):
                    field.fill(value, timeout=4000)
                    return True
            except PlaywrightError:
                continue
        return False

    @staticmethod
    def fill_by_labels(page: Page, labels: tuple[str, ...], value: str) -> bool:
        """Füllt ein Feld anhand seines (Teil-)Labels, deutsch oder englisch."""
        for label in labels:
            try:
                field = page.get_by_label(label, exact=False).first
                if field.is_visible(timeout=1500):
                    field.fill(value, timeout=4000)
                    return True
            except PlaywrightError:
                continue
        return False

    @staticmethod
    def upload_first(page: Page, selectors: tuple[str, ...], file_path: str) -> bool:
        for selector in selectors:
            try:
                field = page.locator(selector).first
                if field.count() > 0:
                    field.set_input_files(file_path, timeout=8000)
                    return True
            except PlaywrightError:
                continue
        return False

    @staticmethod
    def click_first(page: Page, selectors: tuple[str, ...]) -> bool:
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=1500):
                    button.click(timeout=4000)
                    return True
            except PlaywrightError:
                continue
        return False
