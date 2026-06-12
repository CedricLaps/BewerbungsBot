"""FastAPI-Anwendung: Weboberfläche, JSON-API und Scheduler-Lifecycle."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from backend.config import AppConfig, load_config
from backend.logger import setup_logging
from backend.pipeline import Pipeline
from backend.scheduler import create_scheduler
from dashboard.schemas import ActionOut, JobDetailOut, JobOut, StatsOut, StatusUpdateIn
from database.db import build_session_factory
from database.models import JobStatus
from database.repository import JobFilter

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Baut die FastAPI-App; eigene Config erleichtert Tests."""
    app_config = config if config is not None else load_config()
    setup_logging(app_config.logs_dir)
    session_factory = build_session_factory(app_config.database_path)
    pipeline = Pipeline(app_config, session_factory)
    scheduler = create_scheduler(app_config, pipeline) if app_config.scheduler_enabled else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if scheduler is not None:
            scheduler.start()
            logger.info("Scheduler gestartet")
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler gestoppt")

    application = FastAPI(title="BewerbungsBot", version="1.0.0", lifespan=lifespan)
    application.state.pipeline = pipeline
    application.state.config = app_config

    # --------------------------------------------------------------- Seiten

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    # ----------------------------------------------------------------- API

    @application.get("/api/jobs", response_model=list[JobOut])
    def list_jobs(
        status: str | None = Query(
            default=None, description="Ein Status oder mehrere kommagetrennt, z.B. matched,manual"
        ),
        remote: bool | None = None,
        region: str | None = Query(default=None, pattern="^(germany|europe)$"),
        q: str | None = None,
        min_score: int | None = Query(default=None, ge=0, le=100),
        applied: bool | None = None,
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> list[JobOut]:
        statuses: tuple[JobStatus, ...] | None = None
        if status:
            try:
                statuses = tuple(
                    JobStatus(part.strip()) for part in status.split(",") if part.strip()
                )
            except ValueError:
                raise HTTPException(status_code=422, detail=f"Unbekannter Status: {status}")
        jobs = pipeline.repository.list_jobs(
            JobFilter(
                statuses=statuses,
                remote=remote,
                region=region,
                text=q,
                min_score=min_score,
                applied=applied,
                limit=limit,
                offset=offset,
            )
        )
        return [JobOut.model_validate(job) for job in jobs]

    @application.get("/api/jobs/{job_id}", response_model=JobDetailOut)
    def job_detail(job_id: int) -> JobDetailOut:
        job = pipeline.repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job nicht gefunden")
        return JobDetailOut.model_validate(job)

    @application.patch("/api/jobs/{job_id}", response_model=JobOut)
    def update_status(job_id: int, payload: StatusUpdateIn) -> JobOut:
        job = pipeline.repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job nicht gefunden")
        pipeline.repository.update_status(job_id, payload.status)
        updated = pipeline.repository.get(job_id)
        if updated is None:  # pragma: no cover - Job kann nicht verschwinden
            raise HTTPException(status_code=404, detail="Job nicht gefunden")
        return JobOut.model_validate(updated)

    @application.get("/api/stats", response_model=StatsOut)
    def stats() -> StatsOut:
        return StatsOut(**pipeline.repository.stats())

    @application.post("/api/scrape", response_model=ActionOut)
    def trigger_scrape(background_tasks: BackgroundTasks) -> ActionOut:
        background_tasks.add_task(pipeline.scrape_and_score)
        return ActionOut(started=True, detail="Jobsuche im Hintergrund gestartet")

    @application.post("/api/apply", response_model=ActionOut)
    def trigger_apply(background_tasks: BackgroundTasks) -> ActionOut:
        background_tasks.add_task(pipeline.apply_pending)
        return ActionOut(started=True, detail="Bewerbungslauf im Hintergrund gestartet")

    @application.post("/api/jobs/{job_id}/apply", response_model=ActionOut)
    def trigger_apply_single(job_id: int, background_tasks: BackgroundTasks) -> ActionOut:
        job = pipeline.repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job nicht gefunden")
        if job.applied:
            raise HTTPException(status_code=409, detail="Bewerbung wurde bereits gesendet")
        background_tasks.add_task(pipeline.apply_single, job_id)
        return ActionOut(started=True, detail=f"Bewerbung für '{job.title}' gestartet")

    return application


app = create_app()
