"""``processing_jobs`` queue repository.

Concurrency-safe claiming via Postgres ``FOR UPDATE SKIP LOCKED`` so multiple
overlapping cron runs (or a cron + a persistent worker) never double-process a
job. The claim transition to ``PROCESSING`` is committed before work begins, so
the row lock is held only for the (sub-millisecond) claim, not for the seconds
of video processing. A stale-``PROCESSING`` reaper (``requeue_stale``) recovers
jobs whose worker died mid-flight.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.db.models import JobStatus, ProcessingJob


@dataclass(frozen=True)
class ClaimedJob:
    """Plain snapshot of a claimed job, safe to use after the session closes."""

    id: uuid.UUID
    wa_phone: str | None
    media_id: str | None
    language: str
    user_id: uuid.UUID | None
    intake: dict[str, Any]
    attempts: int
    max_attempts: int


def _now() -> datetime:
    return datetime.now(UTC)


async def enqueue(
    db: AsyncSession,
    *,
    media_id: str | None = None,
    channel: str = "WHATSAPP",
    wa_phone: str | None = None,
    wa_message_id: str | None = None,
    language: str = "en",
    user_id: uuid.UUID | None = None,
    intake: dict[str, Any] | None = None,
    max_attempts: int = 3,
) -> ProcessingJob:
    """Insert a QUEUED job (called by the webhook). Returns the flushed row.

    ``channel`` partitions the queue: the WhatsApp runner only claims
    ``WHATSAPP`` jobs, so a ``KIOSK`` job (which carries derived signals in
    ``intake`` rather than a ``media_id``) waits for the kiosk worker instead of
    being failed for a missing media id.
    """
    job = ProcessingJob(
        status=JobStatus.QUEUED,
        channel=channel,
        wa_phone=wa_phone,
        wa_message_id=wa_message_id,
        media_id=media_id,
        language=language,
        user_id=user_id,
        intake=intake or {},
        max_attempts=max_attempts,
    )
    db.add(job)
    await db.flush()
    return job


def _scrub_rows(rows: Sequence[ProcessingJob]) -> None:
    """Strip PII from job rows in place (right-to-erasure / data minimisation).

    Cancels any not-yet-terminal work so the worker skips it, deletes any
    downloaded media still on disk, and nulls the phone / media / intake /
    result fields. Leaves the row (for the audit trail) but holding no PII.
    """
    for job in rows:
        if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
            job.status = JobStatus.REJECTED
            job.error = "purged_by_subject"
            job.next_attempt_at = None
            job.locked_at = None
        if job.media_path:
            with contextlib.suppress(OSError):
                Path(job.media_path).unlink()
        job.wa_phone = None
        job.media_id = None
        job.media_path = None
        job.intake = {}
        job.result = {}


async def scrub_phone(db: AsyncSession, phone: str) -> int:
    """Erase every job tied to a WhatsApp phone (the STOP/DELETE command).

    Returns the number of jobs scrubbed.
    """
    rows = (
        await db.scalars(select(ProcessingJob).where(ProcessingJob.wa_phone == phone))
    ).all()
    _scrub_rows(rows)
    return len(rows)


async def scrub_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Erase every job linked to a user account (account-erasure coverage).

    Returns the number of jobs scrubbed.
    """
    rows = (
        await db.scalars(select(ProcessingJob).where(ProcessingJob.user_id == user_id))
    ).all()
    _scrub_rows(rows)
    return len(rows)


async def claim_next_batch(
    db: AsyncSession, *, limit: int, channel: str = "WHATSAPP"
) -> list[ClaimedJob]:
    """Atomically claim up to ``limit`` eligible jobs and mark them PROCESSING.

    Eligible = QUEUED, matching ``channel``, and (no backoff set or backoff
    elapsed). The caller's transaction must commit to release the row locks and
    persist the PROCESSING transition before processing begins.
    """
    now = _now()
    stmt = (
        select(ProcessingJob)
        .where(
            ProcessingJob.status == JobStatus.QUEUED,
            ProcessingJob.channel == channel,
            or_(
                ProcessingJob.next_attempt_at.is_(None),
                ProcessingJob.next_attempt_at <= now,
            ),
        )
        .order_by(
            ProcessingJob.next_attempt_at.asc().nulls_first(),
            ProcessingJob.created_at.asc(),
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = (await db.execute(stmt)).scalars().all()
    claimed: list[ClaimedJob] = []
    for job in rows:
        job.status = JobStatus.PROCESSING
        job.locked_at = now
        job.attempts += 1
        claimed.append(
            ClaimedJob(
                id=job.id,
                wa_phone=job.wa_phone,
                media_id=job.media_id,
                language=job.language,
                user_id=job.user_id,
                intake=dict(job.intake),
                attempts=job.attempts,
                max_attempts=job.max_attempts,
            )
        )
    await db.flush()
    return claimed


async def set_media_path(
    db: AsyncSession, job_id: uuid.UUID, media_path: str
) -> None:
    job = await db.get(ProcessingJob, job_id)
    if job is not None:
        job.media_path = media_path


async def mark_succeeded(
    db: AsyncSession,
    job_id: uuid.UUID,
    *,
    result: dict[str, Any],
) -> None:
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = JobStatus.SUCCEEDED
    job.result = result
    job.error = None
    job.processed_at = _now()


async def mark_rejected(
    db: AsyncSession,
    job_id: uuid.UUID,
    *,
    result: dict[str, Any],
) -> None:
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        return
    job.status = JobStatus.REJECTED
    job.result = result
    job.processed_at = _now()


async def mark_failed_or_retry(
    db: AsyncSession,
    job_id: uuid.UUID,
    *,
    error: str,
    backoff_s: int,
) -> JobStatus:
    """Re-queue with backoff if attempts remain, else mark FAILED.

    Returns the resulting status so the runner knows whether to send the
    user-facing error message (only on terminal FAILED, never on a retry).
    """
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        return JobStatus.FAILED
    job.error = error[:4000]
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.processed_at = _now()
    else:
        job.status = JobStatus.QUEUED
        job.locked_at = None
        job.next_attempt_at = _now() + timedelta(seconds=backoff_s * job.attempts)
    return job.status


async def requeue_stale(
    db: AsyncSession, *, older_than_s: int = 600
) -> int:
    """Recover jobs stuck in PROCESSING (worker died) back to QUEUED."""
    cutoff = _now() - timedelta(seconds=older_than_s)
    stmt = select(ProcessingJob).where(
        ProcessingJob.status == JobStatus.PROCESSING,
        ProcessingJob.locked_at < cutoff,
    )
    rows = (await db.execute(stmt)).scalars().all()
    for job in rows:
        job.status = JobStatus.QUEUED
        job.locked_at = None
    return len(rows)
