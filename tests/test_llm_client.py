"""Tests für den Ollama-Client (mit gemocktem requests-Modul)."""
from __future__ import annotations

import pytest

import backend.llm_client as llm_module
import backend.retry as retry_module
from backend.config import AppConfig
from backend.llm_client import LLMClient, LLMError, LLMUnavailableError


def make_client(config: AppConfig) -> LLMClient:
    return LLMClient(config)


def patch_post(monkeypatch: pytest.MonkeyPatch, fake_response_class: type, response_text: str) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> object:
        return fake_response_class(status_code=200, json_data={"response": response_text})

    monkeypatch.setattr(llm_module.requests, "post", fake_post)


def test_clean_strips_deepseek_think_blocks() -> None:
    raw = "<think>Lange interne Überlegung …</think>\nHallo Welt"
    assert LLMClient._clean(raw) == "Hallo Welt"


def test_clean_strips_code_fences() -> None:
    raw = "```json\n{\"score\": 80}\n```"
    assert "```" not in LLMClient._clean(raw)


def test_calculate_match_score_parses_json(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, fake_response_class: type
) -> None:
    patch_post(monkeypatch, fake_response_class, '<think>hm</think>{"score": 85}')
    client = make_client(config)
    assert client.calculate_match_score("Java Developer", "Spring Boot Backend") == 85


def test_calculate_match_score_falls_back_to_first_integer(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, fake_response_class: type
) -> None:
    patch_post(monkeypatch, fake_response_class, "Ich schätze die Passung auf 72 von 100 Punkten.")
    client = make_client(config)
    assert client.calculate_match_score("Java Developer", "Beschreibung") == 72


def test_calculate_match_score_clamps_to_100(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, fake_response_class: type
) -> None:
    patch_post(monkeypatch, fake_response_class, '{"score": 250}')
    client = make_client(config)
    assert client.calculate_match_score("x", "y") == 100


def test_generate_cover_letter_limits_words(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, fake_response_class: type
) -> None:
    long_text = " ".join(["Wort"] * 400) + ". Ende hier."
    patch_post(monkeypatch, fake_response_class, long_text)
    client = make_client(config)
    letter = client.generate_cover_letter("Java Developer", "Acme GmbH", "Java und Spring Boot")
    assert len(letter.split()) <= 250


def test_generate_cover_letter_raises_on_empty_response(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, fake_response_class: type
) -> None:
    patch_post(monkeypatch, fake_response_class, "<think>nur Gedanken</think>")
    client = make_client(config)
    with pytest.raises(LLMError):
        client.generate_cover_letter("Java Developer", "Acme GmbH", "Beschreibung")


def test_unreachable_ollama_raises_unavailable(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_post(url: str, json: dict, timeout: int) -> object:
        raise llm_module.requests.ConnectionError("connection refused")

    monkeypatch.setattr(llm_module.requests, "post", failing_post)
    monkeypatch.setattr(retry_module.time, "sleep", lambda _: None)
    client = make_client(config)
    with pytest.raises(LLMUnavailableError):
        client._generate("test")


def test_analyse_job_falls_back_on_garbage(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, fake_response_class: type
) -> None:
    patch_post(monkeypatch, fake_response_class, "keine strukturierte Antwort")
    client = make_client(config)
    analysis = client.analyse_job(
        "Java Developer", "Remote-Stelle: Wir suchen Verstärkung für unser Team in Deutschland."
    )
    assert analysis.language == "de"
    assert analysis.remote is True


def test_analyse_job_parses_valid_json(
    config: AppConfig, monkeypatch: pytest.MonkeyPatch, fake_response_class: type
) -> None:
    payload = (
        '{"technologies": ["Java", "Spring Boot"], "seniority": "junior", '
        '"language": "de", "remote": true, "summary": "Junior-Java-Stelle"}'
    )
    patch_post(monkeypatch, fake_response_class, payload)
    client = make_client(config)
    analysis = client.analyse_job("Java Developer", "Beschreibung")
    assert analysis.technologies == ["Java", "Spring Boot"]
    assert analysis.seniority == "junior"
    assert analysis.remote is True


def test_limit_words_keeps_short_text() -> None:
    assert LLMClient._limit_words("Kurzer Text.", 250) == "Kurzer Text."


def test_cover_letter_prompt_includes_style_samples(
    config: AppConfig,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    fake_response_class: type,
) -> None:
    import dataclasses

    (tmp_path / "beispiel.txt").write_text(
        "Mein Stil ist prägnant und direkt.", encoding="utf-8"
    )
    cfg = dataclasses.replace(config, cover_letter_samples_path=str(tmp_path))
    captured: dict[str, str] = {}

    def capturing_post(url: str, json: dict, timeout: int) -> object:
        captured["prompt"] = json["prompt"]
        return fake_response_class(
            status_code=200, json_data={"response": "Sehr geehrtes Team, Anschreiben."}
        )

    monkeypatch.setattr(llm_module.requests, "post", capturing_post)
    client = LLMClient(cfg)
    client.generate_cover_letter("Java Developer", "Acme GmbH", "Wir suchen Java und Spring.")
    assert "Mein Stil ist prägnant und direkt." in captured["prompt"]
    assert "wörtlich" in captured["prompt"]
