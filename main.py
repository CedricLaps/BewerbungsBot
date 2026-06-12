"""CLI-Einstiegspunkt: Dashboard starten, Suche/Bewerbung manuell anstoßen, Statistiken."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.config import AppConfig, load_config
from backend.logger import get_logger, setup_logging


def _build_pipeline(config: AppConfig):
    from backend.pipeline import Pipeline
    from database.db import build_session_factory

    return Pipeline(config, build_session_factory(config.database_path))


def cmd_serve(config: AppConfig) -> int:
    import uvicorn

    uvicorn.run("dashboard.app:app", host=config.host, port=config.port, log_level="info")
    return 0


def cmd_scrape(config: AppConfig) -> int:
    result = _build_pipeline(config).scrape_and_score()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_apply(config: AppConfig, limit: int | None) -> int:
    result = _build_pipeline(config).apply_pending(limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_score(config: AppConfig, rescore_all: bool) -> int:
    pipeline = _build_pipeline(config)
    result = pipeline.rescore_unapplied() if rescore_all else pipeline.score_new_jobs()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_stats(config: AppConfig) -> int:
    stats = _build_pipeline(config).repository.stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


def cmd_workday_login(config: AppConfig, url: str) -> int:
    """Öffnet einen sichtbaren Browser zur Workday-Anmeldung und speichert die Sitzung."""
    from playwright.sync_api import sync_playwright

    state_path = Path(config.workday_storage_state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        print("Bitte im geöffneten Browser bei Workday anmelden.")
        input("Danach hier ENTER drücken, um die Sitzung zu speichern … ")
        context.storage_state(path=str(state_path))
        browser.close()
    print(f"Sitzung gespeichert: {state_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bewerbungsbot",
        description="Bewerbungsautomatisierung: Jobs sammeln, bewerten und bewerben.",
    )
    parser.add_argument("--config", default=None, help="Pfad zur config.json")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Dashboard mit Scheduler starten (Standard)")
    subparsers.add_parser("scrape", help="Einmalig Jobs sammeln und bewerten")
    apply_parser = subparsers.add_parser("apply", help="Einmalig Bewerbungen versenden")
    apply_parser.add_argument("--limit", type=int, default=None, help="Maximale Anzahl Bewerbungen")
    score_parser = subparsers.add_parser("score", help="Unbewertete Jobs bewerten")
    score_parser.add_argument(
        "--all",
        action="store_true",
        dest="rescore_all",
        help="Auch bereits bewertete (nicht beworbene) Jobs neu bewerten",
    )
    subparsers.add_parser("stats", help="Statistiken ausgeben")
    login_parser = subparsers.add_parser(
        "workday-login", help="Workday-Sitzung interaktiv speichern"
    )
    login_parser.add_argument("url", help="URL des Workday-Karriereportals")

    args = parser.parse_args(argv)
    config = load_config(args.config)
    setup_logging(config.logs_dir)
    log = get_logger("main")
    log.info("Befehl: %s", args.command or "serve")

    match args.command:
        case "scrape":
            return cmd_scrape(config)
        case "apply":
            return cmd_apply(config, args.limit)
        case "score":
            return cmd_score(config, args.rescore_all)
        case "stats":
            return cmd_stats(config)
        case "workday-login":
            return cmd_workday_login(config, args.url)
        case _:
            return cmd_serve(config)


if __name__ == "__main__":
    sys.exit(main())
