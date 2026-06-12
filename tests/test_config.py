"""Tests für das Konfigurationssystem."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import AppConfig, WorkdaySite, load_config


def test_defaults_match_spec() -> None:
    config = AppConfig()
    assert config.llm_provider == "ollama"
    assert config.ollama_model == "deepseek-r1"
    assert config.ollama_url == "http://localhost:11434/api/generate"
    assert config.min_match_score == 60
    assert "Java Developer" in config.search_keywords
    assert "SAP" in config.negative_keywords


def test_from_dict_ignores_unknown_keys() -> None:
    config = AppConfig.from_dict({"unbekannt": 1, "firstname": "Max"})
    assert config.firstname == "Max"


def test_from_dict_converts_lists_to_tuples() -> None:
    config = AppConfig.from_dict({"positive_keywords": ["Java", "Spring"]})
    assert config.positive_keywords == ("Java", "Spring")


def test_from_dict_parses_workday_sites() -> None:
    config = AppConfig.from_dict(
        {"workday_sites": [{"host": "acme.wd3.myworkdayjobs.com", "site": "External", "company": "Acme"}]}
    )
    assert config.workday_sites == (
        WorkdaySite(host="acme.wd3.myworkdayjobs.com", site="External", company="Acme"),
    )
    assert config.workday_sites[0].tenant == "acme"


def test_load_config_reads_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"firstname": "Cedric", "city": "Geldern", "min_match_score": 70}),
        encoding="utf-8",
    )
    config = load_config(config_file)
    assert config.firstname == "Cedric"
    assert config.min_match_score == 70


def test_load_config_missing_file_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nicht-vorhanden.json")
    assert config.ollama_model == "deepseek-r1"


def test_env_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"headless": True}), encoding="utf-8")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434/api/generate")
    monkeypatch.setenv("HEADLESS", "false")
    monkeypatch.setenv("DASHBOARD_PORT", "9000")
    config = load_config(config_file)
    assert config.ollama_url == "http://ollama:11434/api/generate"
    assert config.headless is False
    assert config.port == 9000


def test_full_name(config: AppConfig) -> None:
    assert config.full_name == "Cedric Lapschies"
