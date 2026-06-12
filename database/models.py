"""SQLAlchemy-Modelle für Jobs und Bewerbungsversuche."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    """Lebenszyklus einer Stelle in der Pipeline."""

    NEW = "new"                # gefunden, noch nicht bewertet
    MATCHED = "matched"        # Score >= Schwelle, bereit zur Bewerbung
    SKIPPED = "skipped"        # Score unter Schwelle
    MANUAL = "manual"          # passend, aber Plattform nicht automatisierbar
    APPLIED = "applied"        # Bewerbung abgesendet
    FAILED = "failed"          # Bewerbungsversuch fehlgeschlagen
    ANSWERED = "answered"      # Antwort erhalten
    INTERVIEW = "interview"    # Einladung zum Gespräch
    REJECTED = "rejected"      # Absage
    OFFER = "offer"            # Angebot


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("url", name="uq_jobs_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(50), index=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    remote: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    language: Mapped[str] = mapped_column(String(5), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    keyword_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=20), default=JobStatus.NEW, index=True
    )
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_received: Mapped[bool] = mapped_column(Boolean, default=False)
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    attempts: Mapped[list["ApplicationAttempt"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Job id={self.id} company={self.company!r} title={self.title!r} status={self.status}>"


class ApplicationAttempt(Base):
    """Protokoll jedes Bewerbungsversuchs (erfolgreich oder gescheitert)."""

    __tablename__ = "application_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(Text, default="")
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    job: Mapped[Job] = relationship(back_populates="attempts")
