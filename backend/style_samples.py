"""Lädt Beispiel-Anschreiben des Bewerbers als Stilvorlagen für die LLM-Generierung."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_SAMPLES = 3
MAX_CHARS_PER_SAMPLE = 1500
_TEXT_SUFFIXES = frozenset({".txt", ".md"})


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf nicht installiert — PDF-Stilvorlage %s übersprungen", path.name)
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # pypdf wirft je nach Datei unterschiedlichste Fehler
        logger.warning("PDF-Stilvorlage %s nicht lesbar: %s", path.name, exc)
        return ""


def load_style_samples(
    directory: str | Path,
    max_samples: int = MAX_SAMPLES,
    max_chars: int = MAX_CHARS_PER_SAMPLE,
) -> list[str]:
    """Liest bis zu `max_samples` Beispiel-Anschreiben (.txt/.md/.pdf) aus dem Ordner.

    Dateien werden alphabetisch geladen und auf `max_chars` Zeichen gekürzt,
    damit der Prompt nicht ausufert. Ein fehlender Ordner ist kein Fehler.
    """
    folder = Path(directory)
    if not folder.is_dir():
        return []
    samples: list[str] = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if len(samples) >= max_samples:
            break
        if not path.is_file() or path.name.lower() == "readme.md":
            continue
        suffix = path.suffix.lower()
        if suffix in _TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Stilvorlage %s nicht lesbar: %s", path.name, exc)
                continue
        elif suffix == ".pdf":
            text = _read_pdf(path)
        else:
            continue
        text = text.strip()
        if text:
            samples.append(text[:max_chars])
    if samples:
        logger.info("%d Stilvorlage(n) aus %s geladen", len(samples), folder)
    return samples


def build_style_block(samples: list[str], language: str) -> str:
    """Baut den Prompt-Abschnitt mit den Stilbeispielen (leer, wenn keine vorhanden)."""
    if not samples:
        return ""
    joined = "\n\n".join(
        f"--- Beispiel {index + 1} ---\n{sample}" for index, sample in enumerate(samples)
    )
    if language == "de":
        return (
            "\n\nSo formuliert der Bewerber üblicherweise. Übernimm Tonfall, Satzbau und "
            "typische Formulierungen aus diesen Beispielen, aber kopiere keine Sätze "
            "wörtlich und übernimm keine Firmen- oder Stellendetails daraus:\n"
            f"{joined}"
        )
    return (
        "\n\nThis is how the applicant usually writes. Match the tone, sentence rhythm "
        "and typical phrasing of these examples, but do not copy sentences verbatim and "
        "do not reuse company or job details from them:\n"
        f"{joined}"
    )
