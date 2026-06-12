"""Gemeinsame Basis für alle Scraper: JobPosting-Datenklasse, HTTP-Session, URL-Bereinigung."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from backend.config import AppConfig
from backend.matching import looks_remote, title_blocked, title_matches

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Tracking-Parameter, die bei der Duplikatserkennung stören
_TRACKING_PARAMS: frozenset[str] = frozenset({
    "refid", "trackingid", "gh_src", "lever-source", "source", "ref",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
})


def clean_url(url: str) -> str:
    """Entfernt Tracking-Parameter und Fragmente, behält funktionale Query-Parameter."""
    parsed = urlparse(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    ]
    return urlunparse(parsed._replace(query=urlencode(kept), fragment=""))


@dataclass
class JobPosting:
    """Normalisierte Stellenanzeige aus einer beliebigen Quelle."""

    title: str
    company: str
    url: str
    source: str
    location: str = ""
    description: str = ""
    remote: bool = False
    posted_at: datetime | None = field(default=None)

    def __post_init__(self) -> None:
        self.title = self.title.strip()
        self.company = self.company.strip()
        self.url = clean_url(self.url.strip())
        self.location = self.location.strip()
        if not self.remote:
            self.remote = looks_remote(self.title, self.location, self.description[:500])


class BaseScraper(ABC):
    """Basisklasse: stellt Session, Logging, Vorfilter und Wartezeiten bereit."""

    name: str = "base"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.log = logging.getLogger(f"scrapers.{self.name}")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        })

    @abstractmethod
    def search(self) -> list[JobPosting]:
        """Sammelt Stellenanzeigen dieser Quelle."""

    def matches(self, title: str) -> bool:
        return title_matches(title, self.config.search_keywords) and not title_blocked(
            title, self.config.title_blocklist
        )

    def pause(self) -> None:
        """Höfliche Wartezeit zwischen Requests."""
        time.sleep(self.config.request_delay_seconds)
