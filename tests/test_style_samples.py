"""Tests für das Laden der Anschreiben-Stilvorlagen."""
from __future__ import annotations

from pathlib import Path

from backend.style_samples import build_style_block, load_style_samples


def test_loads_text_files_alphabetically(tmp_path: Path) -> None:
    (tmp_path / "b_zweites.txt").write_text("Zweites Beispiel.", encoding="utf-8")
    (tmp_path / "a_erstes.txt").write_text("Erstes Beispiel.", encoding="utf-8")
    samples = load_style_samples(tmp_path)
    assert samples == ["Erstes Beispiel.", "Zweites Beispiel."]


def test_limits_sample_count_and_length(tmp_path: Path) -> None:
    for index in range(5):
        (tmp_path / f"brief{index}.txt").write_text("x" * 5000, encoding="utf-8")
    samples = load_style_samples(tmp_path, max_samples=3, max_chars=100)
    assert len(samples) == 3
    assert all(len(sample) == 100 for sample in samples)


def test_ignores_readme_and_unknown_formats(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Anleitung", encoding="utf-8")
    (tmp_path / "foto.png").write_bytes(b"\x89PNG")
    (tmp_path / "brief.txt").write_text("Echter Inhalt.", encoding="utf-8")
    assert load_style_samples(tmp_path) == ["Echter Inhalt."]


def test_missing_directory_returns_empty(tmp_path: Path) -> None:
    assert load_style_samples(tmp_path / "gibtsnicht") == []


def test_build_style_block_empty_without_samples() -> None:
    assert build_style_block([], "de") == ""


def test_build_style_block_contains_samples_and_instruction() -> None:
    block = build_style_block(["Mein Stil ist prägnant."], "de")
    assert "Mein Stil ist prägnant." in block
    assert "wörtlich" in block
    english = build_style_block(["My concise style."], "en")
    assert "My concise style." in english
    assert "verbatim" in english
