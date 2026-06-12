"""Lokaler LLM-Client (Ollama) für Stellenanalyse, Match-Scoring und Anschreiben."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import requests

from backend.config import AppConfig
from backend.language import detect_language
from backend.retry import retry

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```[a-zA-Z]*\n?|```", re.MULTILINE)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_INT_RE = re.compile(r"\b(\d{1,3})\b")
_SENTENCE_END = (".", "!", "?")

MAX_COVER_LETTER_WORDS = 250
_MAX_DESCRIPTION_CHARS = 5000


class LLMError(RuntimeError):
    """Das lokale LLM hat eine unbrauchbare Antwort geliefert."""


class LLMUnavailableError(LLMError):
    """Der Ollama-Endpunkt ist nicht erreichbar."""


@dataclass
class JobAnalysis:
    """Strukturierte LLM-Analyse einer Stellenanzeige."""

    technologies: list[str] = field(default_factory=list)
    seniority: str = "unknown"
    language: str = "en"
    remote: bool = False
    summary: str = ""


class LLMClient:
    """Spricht den lokalen Ollama-Server an (konfiguriert über config.json)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.model = config.ollama_model
        self.url = config.ollama_url
        self.timeout = config.llm_timeout_seconds

    @property
    def base_url(self) -> str:
        return self.url.split("/api/")[0]

    def is_available(self) -> bool:
        """Prüft, ob der Ollama-Server antwortet."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    @retry(attempts=2, delay=3.0, backoff=2.0, exceptions=(LLMUnavailableError,))
    def _generate(self, prompt: str, temperature: float = 0.4) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMUnavailableError(f"Ollama nicht erreichbar unter {self.url}: {exc}") from exc
        if response.status_code != 200:
            raise LLMError(f"Ollama HTTP {response.status_code}: {response.text[:300]}")
        raw = str(response.json().get("response", ""))
        return self._clean(raw)

    @staticmethod
    def _clean(text: str) -> str:
        """Entfernt <think>-Blöcke (deepseek-r1) und Markdown-Codezäune."""
        text = _THINK_RE.sub("", text)
        text = _CODE_FENCE_RE.sub("", text)
        return text.strip()

    @staticmethod
    def _extract_json(text: str) -> dict[str, object]:
        match = _JSON_RE.search(text)
        if not match:
            raise LLMError(f"Keine JSON-Antwort gefunden: {text[:200]!r}")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"Ungültiges JSON vom LLM: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError("JSON-Antwort ist kein Objekt")
        return data

    def _profile_summary(self) -> str:
        skills = ", ".join(self.config.profile_skills)
        experience = "; ".join(self.config.profile_experience)
        return (
            f"Name: {self.config.full_name}. "
            f"Technologien: {skills}. "
            f"Erfahrung: {experience}. "
            f"Wohnort: {self.config.city}, {self.config.country}. "
            f"GitHub: {self.config.github}."
        )

    # ------------------------------------------------------------------ API

    def analyse_job(self, title: str, description: str) -> JobAnalysis:
        """Analysiert eine Stellenanzeige; fällt bei LLM-Fehlern auf Heuristiken zurück."""
        text = f"{title}\n{description}"
        fallback = JobAnalysis(
            language=detect_language(text),
            remote="remote" in text.lower(),
            summary=title,
        )
        prompt = (
            "Analysiere die folgende Stellenanzeige. Antworte AUSSCHLIESSLICH mit einem "
            "JSON-Objekt mit genau diesen Schlüsseln: "
            '{"technologies": [Liste der geforderten Technologien], '
            '"seniority": "junior"|"mid"|"senior", '
            '"language": "de"|"en", '
            '"remote": true|false, '
            '"summary": "Zusammenfassung in einem Satz"}\n\n'
            f"Titel: {title}\n\nAnzeige:\n{description[:_MAX_DESCRIPTION_CHARS]}"
        )
        try:
            answer = self._generate(prompt, temperature=0.2)
            data = self._extract_json(answer)
        except LLMError as exc:
            logger.warning("analyse_job: Fallback auf Heuristik (%s)", exc)
            return fallback

        technologies_raw = data.get("technologies")
        technologies = (
            [str(item) for item in technologies_raw] if isinstance(technologies_raw, list) else []
        )
        seniority = str(data.get("seniority", fallback.seniority)).lower()
        language = str(data.get("language", fallback.language)).lower()[:2]
        if language not in ("de", "en"):
            language = fallback.language
        return JobAnalysis(
            technologies=technologies,
            seniority=seniority if seniority in ("junior", "mid", "senior") else "unknown",
            language=language,
            remote=bool(data.get("remote", fallback.remote)),
            summary=str(data.get("summary", fallback.summary)),
        )

    def calculate_match_score(self, title: str, description: str) -> int:
        """LLM-Einschätzung (0–100), wie gut die Stelle zum Bewerberprofil passt."""
        prompt = (
            "Du bist Recruiting-Experte. Bewerte auf einer Skala von 0 bis 100, wie gut "
            "die folgende Stellenanzeige zu diesem Bewerberprofil passt. "
            "Junior-/Mid-Level-Stellen mit Java, Spring Boot oder Angular passen sehr gut; "
            "Stellen mit SAP, COBOL, Embedded oder Anforderungen ab 10 Jahren Erfahrung "
            "passen schlecht.\n\n"
            f"Bewerberprofil: {self._profile_summary()}\n\n"
            f"Stellenanzeige:\nTitel: {title}\n{description[:_MAX_DESCRIPTION_CHARS]}\n\n"
            'Antworte AUSSCHLIESSLICH mit JSON: {"score": <Zahl 0-100>}'
        )
        answer = self._generate(prompt, temperature=0.1)
        try:
            data = self._extract_json(answer)
            score = int(str(data["score"]))
        except (LLMError, KeyError, TypeError, ValueError):
            match = _INT_RE.search(answer)
            if not match:
                raise LLMError(f"Kein Score in LLM-Antwort: {answer[:200]!r}")
            score = int(match.group(1))
        return max(0, min(100, score))

    def generate_cover_letter(self, title: str, company: str, description: str) -> str:
        """Erzeugt ein individuelles Anschreiben (max. 250 Wörter, Sprache automatisch)."""
        language = detect_language(f"{title}\n{description}")
        profile = self._profile_summary()
        if language == "de":
            prompt = (
                f"Schreibe ein individuelles Bewerbungsanschreiben auf Deutsch für die Stelle "
                f"'{title}' bei {company}.\n\n"
                f"Bewerberprofil: {profile}\n\n"
                f"Stellenanzeige:\n{description[:_MAX_DESCRIPTION_CHARS]}\n\n"
                "Anforderungen an das Anschreiben:\n"
                f"- Maximal {MAX_COVER_LETTER_WORDS} Wörter\n"
                "- Geht konkret auf Anforderungen der Stellenanzeige ein\n"
                "- Nennt passende Technologien und Erfahrungen aus dem Profil\n"
                "- Keine Standardfloskeln wie 'hiermit bewerbe ich mich'\n"
                "- Professioneller, natürlicher Ton\n"
                "- Beginnt mit einer Anrede, endet mit 'Mit freundlichen Grüßen' und dem Namen\n"
                "- Gib NUR den Anschreiben-Text aus, ohne Betreff, Kommentare oder Platzhalter"
            )
        else:
            prompt = (
                f"Write an individual cover letter in English for the position "
                f"'{title}' at {company}.\n\n"
                f"Applicant profile: {profile}\n\n"
                f"Job posting:\n{description[:_MAX_DESCRIPTION_CHARS]}\n\n"
                "Requirements for the letter:\n"
                f"- Maximum {MAX_COVER_LETTER_WORDS} words\n"
                "- Address concrete requirements from the job posting\n"
                "- Mention matching technologies and experience from the profile\n"
                "- No generic boilerplate phrases\n"
                "- Professional, natural tone\n"
                "- Start with a salutation, end with 'Kind regards' and the name\n"
                "- Output ONLY the letter text, no subject line, comments or placeholders"
            )
        letter = self._generate(prompt, temperature=0.6)
        if not letter:
            raise LLMError("LLM hat ein leeres Anschreiben geliefert")
        return self._limit_words(letter, MAX_COVER_LETTER_WORDS)

    @staticmethod
    def _limit_words(text: str, max_words: int) -> str:
        """Kürzt auf max_words Wörter, möglichst am letzten Satzende."""
        words = text.split()
        if len(words) <= max_words:
            return text.strip()
        truncated = " ".join(words[:max_words])
        last_end = max(truncated.rfind(char) for char in _SENTENCE_END)
        if last_end > len(truncated) // 2:
            truncated = truncated[: last_end + 1]
        return truncated.strip()
