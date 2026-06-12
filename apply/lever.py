"""Applier für Lever-Bewerbungsformulare (jobs.lever.co)."""
from __future__ import annotations

from playwright.sync_api import Page

from apply.base import ApplyError, BaseApplier
from database.models import Job


class LeverApplier(BaseApplier):
    name = "lever"

    def can_handle(self, url: str) -> bool:
        return "jobs.lever.co" in url

    def fill_form(self, page: Page, job: Job, cover_letter: str) -> None:
        config = self.config

        # Von der Stellenbeschreibung zum Bewerbungsformular wechseln
        if not page.url.rstrip("/").endswith("/apply"):
            page.goto(job.url.rstrip("/") + "/apply", wait_until="domcontentloaded")
            self.dismiss_cookie_banner(page)

        if not self.fill_first(page, ("input[name='name']",), config.full_name):
            raise ApplyError("Namensfeld nicht gefunden — kein Lever-Standardformular")
        self.fill_first(page, ("input[name='email']",), config.email)
        self.fill_first(page, ("input[name='phone']",), config.phone)
        self.fill_first(
            page, ("input[name='location']",), f"{config.city}, {config.country}"
        )
        self.fill_first(page, ("input[name='urls[GitHub]']",), config.github)
        self.fill_first(page, ("input[name='urls[LinkedIn]']",), config.linkedin)

        uploaded = self.upload_first(
            page,
            ("input[name='resume']", "#resume-upload-input", "input[type='file']"),
            config.cv_path,
        )
        if not uploaded:
            raise ApplyError("Kein Lebenslauf-Upload gefunden")
        # Lever parst den Lebenslauf nach dem Upload kurz serverseitig
        page.wait_for_timeout(3000)

        if not self.fill_first(page, ("textarea[name='comments']",), cover_letter):
            self.log.warning("Kein Anschreiben-Feld gefunden — Bewerbung läuft ohne Anschreiben")

    def submit_selectors(self) -> tuple[str, ...]:
        return (
            "button#btn-submit",
            "button[data-qa='btn-submit']",
            "button:has-text('Submit application')",
        )
