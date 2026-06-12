"""Erkennung unterstützter Bewerbungsplattformen (ATS) anhand der URL."""
from __future__ import annotations

# Muss zu den can_handle()-Prüfungen der Applier in apply/ passen
SUPPORTED_ATS_MARKERS: tuple[str, ...] = (
    "greenhouse.io",
    "jobs.lever.co",
    "jobs.personio.de",
    "jobs.personio.com",
    "myworkdayjobs.com",
)


def is_supported_ats(url: str) -> bool:
    """Ob die URL auf eine Plattform zeigt, auf der der Bot automatisch bewerben kann."""
    lowered = url.lower()
    return any(marker in lowered for marker in SUPPORTED_ATS_MARKERS)
