"""APScheduler-Konfiguration für regelmäßige Scrape- und Bewerbungsläufe."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import AppConfig
from backend.pipeline import Pipeline

logger = logging.getLogger(__name__)


def create_scheduler(config: AppConfig, pipeline: Pipeline) -> BackgroundScheduler:
    """Erzeugt den Hintergrund-Scheduler (Start übernimmt der Aufrufer)."""
    scheduler = BackgroundScheduler(timezone="Europe/Berlin")
    scheduler.add_job(
        pipeline.scrape_and_score,
        trigger="interval",
        hours=config.scrape_interval_hours,
        id="scrape",
        name="Stellen sammeln und bewerten",
        # Zeitzonenbewusst, sonst interpretiert APScheduler die UTC-Containerzeit
        # als Berlin-Zeit und überspringt den ersten Lauf als "verpasst"
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=1),
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        pipeline.apply_pending,
        trigger="interval",
        hours=config.apply_interval_hours,
        id="apply",
        name="Bewerbungen versenden",
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=10),
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Scheduler konfiguriert: Scrape alle %dh, Bewerbungen alle %dh",
        config.scrape_interval_hours,
        config.apply_interval_hours,
    )
    return scheduler
