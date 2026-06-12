"""Applier für Greenhouse-Bewerbungsformulare (klassisches und neues Board-Layout)."""
from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from apply.base import ApplyError, BaseApplier
from database.models import Job


class GreenhouseApplier(BaseApplier):
    name = "greenhouse"

    def can_handle(self, url: str) -> bool:
        return "greenhouse.io" in url

    def fill_form(self, page: Page, job: Job, cover_letter: str) -> None:
        config = self.config

        filled_first = self.fill_first(
            page,
            ("#first_name", "input[name='first_name']", "input[name*='first_name']"),
            config.firstname,
        ) or self.fill_by_labels(page, ("First name", "Vorname"), config.firstname)
        if not filled_first:
            raise ApplyError("Vorname-Feld nicht gefunden — kein Greenhouse-Standardformular")

        self.fill_first(
            page,
            ("#last_name", "input[name='last_name']", "input[name*='last_name']"),
            config.lastname,
        ) or self.fill_by_labels(page, ("Last name", "Nachname"), config.lastname)

        self.fill_first(
            page, ("#email", "input[name='email']", "input[type='email']"), config.email
        ) or self.fill_by_labels(page, ("Email", "E-Mail"), config.email)

        self.fill_first(
            page, ("#phone", "input[name='phone']", "input[type='tel']"), config.phone
        ) or self.fill_by_labels(page, ("Phone", "Telefon"), config.phone)

        uploaded = self.upload_first(
            page,
            (
                "input[type='file'][name='resume']",
                "input[type='file'][id*='resume']",
                "input[type='file']",
            ),
            config.cv_path,
        )
        if not uploaded:
            raise ApplyError("Kein Datei-Upload für den Lebenslauf gefunden")

        self._insert_cover_letter(page, cover_letter)

        self.fill_by_labels(page, ("LinkedIn",), config.linkedin)
        self.fill_by_labels(page, ("GitHub", "Website", "Portfolio"), config.github)
        self.fill_by_labels(page, ("Location", "Stadt", "City"), f"{config.city}, {config.country}")

    def _insert_cover_letter(self, page: Page, cover_letter: str) -> None:
        # "Enter manually"-Umschalter des neuen Layouts aktivieren, falls vorhanden
        try:
            toggle = page.locator(
                "button:has-text('enter manually'), button:has-text('Enter manually')"
            ).last
            if toggle.is_visible(timeout=1500):
                toggle.click(timeout=3000)
        except PlaywrightError:
            pass
        inserted = self.fill_first(
            page,
            (
                "#cover_letter_text",
                "textarea[name='cover_letter_text']",
                "textarea[name*='cover_letter']",
                "textarea[id*='cover_letter']",
            ),
            cover_letter,
        ) or self.fill_by_labels(page, ("Cover letter", "Anschreiben"), cover_letter)
        if not inserted:
            self.log.warning("Kein Anschreiben-Feld gefunden — Bewerbung läuft ohne Anschreiben")

    def submit_selectors(self) -> tuple[str, ...]:
        return (
            "#submit_app",
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button:has-text('Bewerbung absenden')",
            "input[type='submit']",
            "button[type='submit']",
        )
