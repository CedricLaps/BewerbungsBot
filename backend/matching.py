"""Keyword-basiertes Matching: Score-Berechnung und Titel-Vorfilter."""
from __future__ import annotations

import re

_BASE_SCORE = 25
_POSITIVE_WEIGHT = 9
_NEGATIVE_WEIGHT = 18
_MAX_POSITIVE_HITS = 8

# Kerntoken für den Titel-Vorfilter, falls keine Suchphrase exakt passt.
# Bewusst kein nacktes "engineer": das ließ "Value Engineer", "System Engineer"
# und "VP Engineering" durch.
_CORE_TITLE_TOKENS: frozenset[str] = frozenset({
    "java", "backend", "spring", "fullstack", "full stack", "full-stack",
    "software engineer", "software developer", "web developer",
    "entwickler", "developer", "informatiker", "programmierer",
    "c#", "csharp", ".net", "dotnet",
})


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    # Wortgrenzen verhindern Treffer wie "rest" in "restaurant";
    # "Java" trifft bewusst nicht "JavaScript" (beides ist ohnehin positiv gelistet).
    return re.compile(rf"(?<!\w){re.escape(keyword.lower())}(?!\w)")


def keyword_score(
    text: str,
    positive_keywords: tuple[str, ...] | list[str],
    negative_keywords: tuple[str, ...] | list[str],
) -> int:
    """Berechnet einen Score von 0–100 aus positiven und negativen Keyword-Treffern."""
    haystack = text.lower()
    positive_hits = sum(
        1 for keyword in positive_keywords if _keyword_pattern(keyword).search(haystack)
    )
    negative_hits = sum(
        1 for keyword in negative_keywords if _keyword_pattern(keyword).search(haystack)
    )
    positive_hits = min(positive_hits, _MAX_POSITIVE_HITS)
    score = _BASE_SCORE + positive_hits * _POSITIVE_WEIGHT - negative_hits * _NEGATIVE_WEIGHT
    return max(0, min(100, score))


def combined_score(kw_score: int, llm_score: int | None) -> int:
    """Kombiniert Keyword- und LLM-Score (je 50 %); ohne LLM zählt nur der Keyword-Score."""
    if llm_score is None:
        return max(0, min(100, kw_score))
    return max(0, min(100, round(0.5 * kw_score + 0.5 * llm_score)))


def title_matches(title: str, search_keywords: tuple[str, ...] | list[str]) -> bool:
    """Vorfilter: passt ein Stellentitel grob zu den Suchbegriffen?"""
    lowered = title.lower()
    if any(keyword.lower() in lowered for keyword in search_keywords):
        return True
    return any(token in lowered for token in _CORE_TITLE_TOKENS)


# Ortsbegriffe, die eine Stelle als "in Deutschland" ausweisen (Substring-Match)
_GERMANY_LOCATION_TERMS: frozenset[str] = frozenset({
    "deutschland", "germany", ", de", "(de)",
    "berlin", "münchen", "munich", "hamburg", "frankfurt", "köln", "cologne",
    "stuttgart", "düsseldorf", "dusseldorf", "leipzig", "dresden", "hannover",
    "nürnberg", "nuremberg", "essen", "dortmund", "bremen", "bonn", "karlsruhe",
    "mannheim", "münster", "aachen", "wiesbaden", "augsburg", "bielefeld",
    "duisburg", "bochum", "wuppertal", "kiel", "rostock", "mainz", "potsdam",
    "erfurt", "magdeburg", "freiburg", "heidelberg", "regensburg", "ulm",
    "würzburg", "kassel", "darmstadt", "paderborn", "ingolstadt", "krefeld",
    "mönchengladbach", "geldern", "kleve", "wesel", "saarbrücken",
})


def location_allowed(location: str, remote: bool) -> bool:
    """Nur Stellen in Deutschland zulassen — außerhalb nur, wenn sie voll remote sind.

    Ein leerer/unbekannter Ort wird durchgelassen; dort entscheidet der Score.
    """
    if remote:
        return True
    lowered = location.lower().strip()
    if not lowered:
        return True
    return any(term in lowered for term in _GERMANY_LOCATION_TERMS)


def title_blocked(title: str, blocklist: tuple[str, ...] | list[str]) -> bool:
    """Harte Sperre für Titel, die eindeutig nicht zum Profil passen (Senior-Level etc.)."""
    lowered = title.lower()
    return any(_keyword_pattern(term).search(lowered) for term in blocklist)


def looks_remote(*parts: str) -> bool:
    """Erkennt Remote-Stellen anhand von Titel/Ort/Beschreibungs-Fragmenten."""
    text = " ".join(parts).lower()
    return any(hint in text for hint in ("remote", "home office", "homeoffice", "home-office"))
