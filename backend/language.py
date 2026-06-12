"""Einfache, abhängigkeitsfreie Spracherkennung (Deutsch/Englisch) über Stoppwort-Häufigkeit."""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-zäöüß]+", re.IGNORECASE)

_GERMAN_HINTS: frozenset[str] = frozenset({
    "und", "der", "die", "das", "wir", "sie", "mit", "für", "ein", "eine",
    "nicht", "werden", "sind", "bei", "ist", "von", "auf", "als", "oder",
    "auch", "zur", "zum", "über", "unser", "unsere", "dein", "deine", "ihre",
    "entwicklung", "kenntnisse", "erfahrung", "aufgaben", "bieten", "profil",
    "team", "stelle", "bewerbung", "möchten", "sowie", "bereich", "arbeiten",
})

_ENGLISH_HINTS: frozenset[str] = frozenset({
    "the", "and", "you", "with", "for", "our", "are", "will", "work",
    "experience", "skills", "of", "to", "in", "we", "as", "your", "team",
    "join", "looking", "about", "have", "build", "what", "who", "role",
    "responsibilities", "requirements", "engineering", "development",
})


def detect_language(text: str) -> str:
    """Gibt 'de' oder 'en' zurück. Bei Gleichstand oder leerem Text: 'en'."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return "en"
    german = sum(1 for w in words if w in _GERMAN_HINTS)
    english = sum(1 for w in words if w in _ENGLISH_HINTS)
    # Umlaute/ß sind ein starkes Signal für Deutsch
    if any(ch in text for ch in "äöüß"):
        german += max(3, len(words) // 100)
    return "de" if german > english else "en"
