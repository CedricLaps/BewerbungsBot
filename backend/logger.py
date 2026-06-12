"""Zentrales Logging: Konsole + rotierende Logdateien unter logs/."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_configured = False


def setup_logging(logs_dir: str | Path = "./logs", level: int = logging.INFO) -> None:
    """Initialisiert Root-Logging idempotent; legt logs/ und logs/screenshots/ an."""
    global _configured
    directory = Path(logs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "screenshots").mkdir(parents=True, exist_ok=True)

    if _configured:
        return

    formatter = logging.Formatter(_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        directory / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    error_handler = logging.handlers.RotatingFileHandler(
        directory / "errors.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(error_handler)
    root.addHandler(console_handler)

    # Bibliotheken etwas leiser stellen
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
