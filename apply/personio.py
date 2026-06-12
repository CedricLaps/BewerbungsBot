"""Applier für Personio-Karriereportale (jobs.personio.de)."""
from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from apply.base import ApplyError, BaseApplier
from database.models import Job


class PersonioApplier(BaseApplier):
    name = "personio"

    def can_handle(self, url: str) -> bool:
        return "jobs.personio.de" in url or "jobs.personio.com" in url

    def fill_form(self, page: Page, job: Job, cover_letter: str) -> None:
        config = self.config

        # Auf der Stellenseite zum Formular springen, falls ein Bewerben-Button existiert
        self.click_first(
            page,
            (
                "a:has-text('Jetzt bewerben')",
                "button:has-text('Jetzt bewerben')",
                "a:has-text('Apply for this position')",
                "button:has-text('Apply')",
            ),
        )
        page.wait_for_timeout(1500)

        filled_first = self.fill_by_labels(
            page, ("Vorname", "First name"), config.firstname
        ) or self.fill_first(page, ("input[name='first_name']",), config.firstname)
        if not filled_first:
            raise ApplyError("Vorname-Feld nicht gefunden — kein Personio-Standardformular")

        self.fill_by_labels(page, ("Nachname", "Last name"), config.lastname) or self.fill_first(
            page, ("input[name='last_name']",), config.lastname
        )
        self.fill_by_labels(page, ("E-Mail", "Email"), config.email) or self.fill_first(
            page, ("input[type='email']", "input[name='email']"), config.email
        )
        self.fill_by_labels(page, ("Telefon", "Phone"), config.phone) or self.fill_first(
            page, ("input[type='tel']", "input[name='phone']"), config.phone
        )

        if not self.upload_first(page, ("input[type='file']",), config.cv_path):
            raise ApplyError("Kein Lebenslauf-Upload gefunden")

        inserted = self.fill_by_labels(
            page, ("Anschreiben", "Cover letter", "Nachricht", "Message"), cover_letter
        ) or self.fill_first(page, ("textarea",), cover_letter)
        if not inserted:
            self.log.warning("Kein Anschreiben-Feld gefunden — Bewerbung läuft ohne Anschreiben")

        self._accept_required_checkboxes(page)

    def _accept_required_checkboxes(self, page: Page) -> None:
        """Hakt Pflicht-Checkboxen an (Datenschutzerklärung), keine optionalen Newsletter."""
        try:
            boxes = page.locator("input[type='checkbox'][required], input[type='checkbox'][aria-required='true']")
            for index in range(boxes.count()):
                box = boxes.nth(index)
                if not box.is_checked():
                    box.check(timeout=3000)
        except PlaywrightError as exc:
            self.log.warning("Pflicht-Checkboxen konnten nicht gesetzt werden: %s", exc)

    def submit_selectors(self) -> tuple[str, ...]:
        return (
            "button[type='submit']",
            "button:has-text('Bewerbung absenden')",
            "button:has-text('Absenden')",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
        )
