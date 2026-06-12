"""Tests für die Spracherkennung."""
from __future__ import annotations

from backend.language import detect_language

GERMAN_TEXT = (
    "Wir suchen einen Entwickler mit guten Kenntnissen in Java und Spring Boot. "
    "Deine Aufgaben umfassen die Entwicklung von REST-Schnittstellen. Wir bieten "
    "flexible Arbeitszeiten und ein motiviertes Team."
)

ENGLISH_TEXT = (
    "We are looking for a developer with strong experience in Java and Spring Boot. "
    "Your responsibilities will include building REST APIs. We offer flexible "
    "working hours and a great team."
)


def test_detects_german() -> None:
    assert detect_language(GERMAN_TEXT) == "de"


def test_detects_english() -> None:
    assert detect_language(ENGLISH_TEXT) == "en"


def test_umlauts_bias_towards_german() -> None:
    assert detect_language("Schöne Grüße aus Köln für die ausgeschriebene Stelle") == "de"


def test_empty_text_defaults_to_english() -> None:
    assert detect_language("") == "en"
    assert detect_language("12345 !!!") == "en"
