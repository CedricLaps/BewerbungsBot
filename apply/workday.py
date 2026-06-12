"""Applier für Workday-Portale (myworkdayjobs.com).

Workday verlangt ein Bewerberkonto. Dieser Applier funktioniert, wenn eine
gespeicherte Browser-Sitzung (storage_state) vorliegt — erzeugbar mit:

    python main.py workday-login https://firma.wdX.myworkdayjobs.com/...

Ohne Sitzung wird der Versuch mit einer klaren Fehlermeldung und Screenshot
abgebrochen, damit die Stelle manuell nachbearbeitet werden kann.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from apply.base import ApplyError, BaseApplier
from database.models import Job

_MAX_STEPS = 6

_FIELD_VALUES_BY_AUTOMATION_ID: tuple[tuple[str, str], ...] = (
    ("legalNameSection_firstName", "firstname"),
    ("legalNameSection_lastName", "lastname"),
    ("addressSection_addressLine1", "city"),
    ("addressSection_city", "city"),
    ("addressSection_postalCode", ""),
    ("email", "email"),
    ("phone-number", "phone"),
)


class WorkdayApplier(BaseApplier):
    name = "workday"

    def can_handle(self, url: str) -> bool:
        return "myworkdayjobs.com" in url

    def context_options(self) -> dict[str, object]:
        options: dict[str, object] = {"locale": "de-DE"}
        state_path = Path(self.config.workday_storage_state)
        if state_path.is_file():
            options["storage_state"] = str(state_path)
        return options

    def fill_form(self, page: Page, job: Job, cover_letter: str) -> None:
        self._start_application(page)
        self._ensure_signed_in(page)
        self._walk_steps(page)

    def _start_application(self, page: Page) -> None:
        started = self.click_first(
            page,
            (
                "a[data-automation-id='adventureButton']",
                "button[data-automation-id='adventureButton']",
                "a:has-text('Apply')",
                "button:has-text('Apply')",
                "a:has-text('Bewerben')",
            ),
        )
        if not started:
            raise ApplyError("Bewerben-Button auf der Workday-Seite nicht gefunden")
        page.wait_for_timeout(2000)
        # Im Auswahl-Dialog die manuelle Bewerbung wählen
        self.click_first(
            page,
            (
                "a[data-automation-id='manualApplyButton']",
                "button[data-automation-id='manualApplyButton']",
                "a:has-text('Apply Manually')",
                "button:has-text('Apply Manually')",
            ),
        )
        page.wait_for_timeout(2000)

    def _ensure_signed_in(self, page: Page) -> None:
        try:
            sign_in_visible = page.locator(
                "[data-automation-id='signInContent'], [data-automation-id='signInFormo'], "
                "input[data-automation-id='password']"
            ).first.is_visible(timeout=3000)
        except PlaywrightError:
            sign_in_visible = False
        if sign_in_visible:
            raise ApplyError(
                "Workday verlangt eine Anmeldung. Bitte einmalig "
                "'python main.py workday-login <URL>' ausführen, um die Sitzung zu speichern."
            )

    def _walk_steps(self, page: Page) -> None:
        """Füllt die mehrseitige Workday-Strecke aus und klickt bis zum Submit."""
        for step in range(_MAX_STEPS):
            self._autofill_current_step(page)
            submit_button = page.locator(
                "button[data-automation-id='bottom-navigation-next-button']:has-text('Submit'), "
                "button[data-automation-id='pageFooterNextButton']:has-text('Submit'), "
                "button[data-automation-id='bottom-navigation-next-button']:has-text('Senden')"
            ).first
            try:
                if submit_button.is_visible(timeout=2000):
                    # Letzter Schritt erreicht; das Absenden übernimmt submit()
                    return
            except PlaywrightError:
                pass
            advanced = self.click_first(
                page,
                (
                    "button[data-automation-id='bottom-navigation-next-button']",
                    "button[data-automation-id='pageFooterNextButton']",
                    "button:has-text('Next')",
                    "button:has-text('Weiter')",
                ),
            )
            if not advanced:
                raise ApplyError(f"Workday-Schritt {step + 1}: kein Weiter-Button gefunden")
            page.wait_for_timeout(3000)
            self._raise_on_validation_errors(page, step)
        raise ApplyError(f"Workday-Strecke nach {_MAX_STEPS} Schritten nicht abgeschlossen")

    def _autofill_current_step(self, page: Page) -> None:
        self.upload_first(
            page,
            ("input[data-automation-id='file-upload-input-ref']", "input[type='file']"),
            self.config.cv_path,
        )
        for automation_id, config_field in _FIELD_VALUES_BY_AUTOMATION_ID:
            if not config_field:
                continue
            value = str(getattr(self.config, config_field, ""))
            if not value:
                continue
            self.fill_first(page, (f"input[data-automation-id='{automation_id}']",), value)

    @staticmethod
    def _raise_on_validation_errors(page: Page, step: int) -> None:
        try:
            error_banner = page.locator("[data-automation-id='errorBanner']").first
            if error_banner.is_visible(timeout=1500):
                text = error_banner.inner_text(timeout=2000)[:300]
                raise ApplyError(f"Workday-Schritt {step + 1} meldet Pflichtfelder: {text}")
        except PlaywrightError:
            return

    def submit_selectors(self) -> tuple[str, ...]:
        return (
            "button[data-automation-id='bottom-navigation-next-button']:has-text('Submit')",
            "button[data-automation-id='pageFooterNextButton']:has-text('Submit')",
            "button[data-automation-id='bottom-navigation-next-button']:has-text('Senden')",
            "button:has-text('Submit')",
        )
