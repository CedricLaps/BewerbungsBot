"""Typisierte Anwendungskonfiguration aus config.json mit Umgebungsvariablen-Overrides."""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

DEFAULT_SEARCH_KEYWORDS: tuple[str, ...] = (
    "Java Developer",
    "Junior Java Developer",
    "Backend Developer",
    "Backend Engineer",
    "Software Engineer",
    "Software Developer",
    "Full Stack Developer",
    "Spring Boot Developer",
    "Application Developer",
    "C# Developer",
    ".NET Developer",
    "Softwareentwickler",
    "Anwendungsentwickler",
)

DEFAULT_LOCATIONS: tuple[str, ...] = ("Deutschland", "Remote", "Europa Remote")

DEFAULT_POSITIVE_KEYWORDS: tuple[str, ...] = (
    "Java", "Spring Boot", "Angular", "REST", "Backend", "MongoDB",
    "Git", "GitLab", "TypeScript", "JUnit", "Fullstack", "POS", "Retail",
    "C#", ".NET", "Unity", "Junior",
)

DEFAULT_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "SAP", "COBOL", "Embedded", "Principal", "Architect", "10+ Jahre", "Senior Lead",
)

# Titel mit diesen Begriffen werden gar nicht erst gespeichert bzw. beim
# Scoring hart aussortiert (Wortgrenzen-Matching, case-insensitive).
DEFAULT_TITLE_BLOCKLIST: tuple[str, ...] = (
    "senior", "principal", "staff", "lead", "head of", "director",
    "vice president", "vp", "chief", "cto", "architect", "architekt",
    "teamleiter", "leiter", "manager",
)

DEFAULT_SKILLS: tuple[str, ...] = (
    "Java", "Spring Boot", "Angular", "TypeScript", "JavaScript",
    "MongoDB", "Git", "GitLab", "JUnit", "REST APIs", "Unity", "C#",
)

DEFAULT_EXPERIENCE: tuple[str, ...] = (
    "Fachinformatiker für Anwendungsentwicklung",
    "Ausbildung bei bofrost*",
    "Erfahrung mit POS-Systemen",
    "Eigene veröffentlichte Software- und Spieleprojekte",
    "GitHub-Projekte",
)


@dataclass(frozen=True)
class WorkdaySite:
    """Ein Workday-Karriereportal, z.B. host='firma.wd3.myworkdayjobs.com', site='External'."""

    host: str
    site: str
    company: str = ""

    @property
    def tenant(self) -> str:
        return self.host.split(".")[0]


@dataclass(frozen=True)
class AppConfig:
    """Gesamte Anwendungskonfiguration (LLM, Bewerberprofil, Suche, Verhalten, Speicher)."""

    # LLM
    llm_provider: str = "ollama"
    ollama_model: str = "deepseek-r1"
    ollama_url: str = "http://localhost:11434/api/generate"
    llm_timeout_seconds: int = 240

    # Bewerberprofil
    firstname: str = "Cedric"
    lastname: str = "Lapschies"
    email: str = ""
    phone: str = ""
    city: str = "Geldern"
    country: str = "Germany"
    salary_expectation: str = "50000"
    cv_path: str = "./documents/CV.pdf"
    certificates_path: str = "./documents/certificates/"
    github: str = "https://github.com/CedricLaps"
    linkedin: str = ""
    profile_skills: tuple[str, ...] = DEFAULT_SKILLS
    profile_experience: tuple[str, ...] = DEFAULT_EXPERIENCE

    # Suche & Matching
    search_keywords: tuple[str, ...] = DEFAULT_SEARCH_KEYWORDS
    locations: tuple[str, ...] = DEFAULT_LOCATIONS
    positive_keywords: tuple[str, ...] = DEFAULT_POSITIVE_KEYWORDS
    negative_keywords: tuple[str, ...] = DEFAULT_NEGATIVE_KEYWORDS
    title_blocklist: tuple[str, ...] = DEFAULT_TITLE_BLOCKLIST
    min_match_score: int = 60
    # Nur Stellen in Deutschland; außerhalb nur, wenn voll remote
    germany_or_remote_only: bool = True

    # Verhalten
    auto_submit: bool = True
    headless: bool = True
    max_applications_per_run: int = 10
    scrape_interval_hours: int = 6
    apply_interval_hours: int = 12
    scheduler_enabled: bool = True
    request_delay_seconds: float = 2.0
    max_pages_per_search: int = 1
    max_descriptions_per_run: int = 20

    # Quellen
    enabled_scrapers: tuple[str, ...] = (
        "linkedin", "stepstone", "indeed", "greenhouse",
        "lever", "personio", "workday", "company_pages",
    )
    greenhouse_boards: tuple[str, ...] = ()
    lever_companies: tuple[str, ...] = ()
    personio_companies: tuple[str, ...] = ()
    workday_sites: tuple[WorkdaySite, ...] = ()
    company_pages: tuple[str, ...] = ()

    # Speicher
    database_path: str = "./data/jobs.db"
    logs_dir: str = "./logs"
    workday_storage_state: str = "./data/workday_state.json"

    # Dashboard
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def full_name(self) -> str:
        return f"{self.firstname} {self.lastname}".strip()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        known = {f.name: f for f in fields(cls)}
        data: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in known:
                continue
            if key == "workday_sites" and isinstance(value, list):
                data[key] = tuple(
                    WorkdaySite(
                        host=str(item.get("host", "")),
                        site=str(item.get("site", "")),
                        company=str(item.get("company", "")),
                    )
                    for item in value
                    if isinstance(item, dict)
                )
            elif isinstance(value, list):
                data[key] = tuple(value)
            else:
                data[key] = value
        return cls(**data)


_ENV_OVERRIDES: dict[str, str] = {
    "OLLAMA_URL": "ollama_url",
    "OLLAMA_MODEL": "ollama_model",
    "DATABASE_PATH": "database_path",
    "LOGS_DIR": "logs_dir",
    "HEADLESS": "headless",
    "AUTO_SUBMIT": "auto_submit",
    "SCHEDULER_ENABLED": "scheduler_enabled",
    "DASHBOARD_HOST": "host",
    "DASHBOARD_PORT": "port",
}

_TRUTHY = {"1", "true", "yes", "on"}


def _coerce(field_name: str, value: str) -> Any:
    field_types = {f.name: f.type for f in dataclasses.fields(AppConfig)}
    declared = str(field_types.get(field_name, "str"))
    if declared == "bool":
        return value.strip().lower() in _TRUTHY
    if declared == "int":
        return int(value)
    if declared == "float":
        return float(value)
    return value


def load_config(path: str | Path | None = None) -> AppConfig:
    """Lädt config.json (Pfad-Parameter > CONFIG_PATH > ./config.json) und wendet ENV-Overrides an."""
    candidate = Path(path) if path else Path(os.environ.get("CONFIG_PATH", "config.json"))
    raw: dict[str, Any] = {}
    if candidate.is_file():
        raw = json.loads(candidate.read_text(encoding="utf-8"))
    config = AppConfig.from_dict(raw)

    overrides: dict[str, Any] = {}
    for env_name, field_name in _ENV_OVERRIDES.items():
        env_value = os.environ.get(env_name)
        if env_value is not None and env_value != "":
            overrides[field_name] = _coerce(field_name, env_value)
    if overrides:
        config = dataclasses.replace(config, **overrides)
    return config
