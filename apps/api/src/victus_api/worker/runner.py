"""Worker runner: claim jobs → fetch media → process → persist → reply.

Each job is handled in isolation (one job's failure never stalls the batch) and
across short transactions: the claim commits the PROCESSING transition, the
heavy rPPG work runs outside any DB transaction, and the terminal status is
written in its own transaction. CPU-bound video processing is offloaded to a
thread so the event loop (and any concurrent I/O) is not blocked.

Entrypoints:
* ``run_once`` — drain currently-eligible jobs and return (cPanel cron).
* ``run_loop`` — poll forever (cPanel persistent Python app).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from pathlib import Path

from victus_api.core.logging import get_logger
from victus_api.db.models import JobStatus, User
from victus_api.db.session import session_scope
from victus_api.toi.schemas import ToiAssessmentRequest
from victus_api.toi.service import assess_toi
from victus_api.worker import jobs
from victus_api.worker.config import WorkerConfig
from victus_api.worker.jobs import ClaimedJob
from victus_api.worker.media import MediaFetcher
from victus_api.worker.processor import CaptureOutcome, CaptureResult, process_capture
from victus_api.worker.reply import Replier

log = get_logger(__name__)


async def run_once(
    cfg: WorkerConfig,
    *,
    fetcher: MediaFetcher,
    replier: Replier,
) -> int:
    """Claim and process one batch. Returns the number of jobs handled."""
    async with session_scope() as db:
        claimed = await jobs.claim_next_batch(db, limit=cfg.batch_size)

    for job in claimed:
        try:
            await _handle_job(cfg, job, fetcher=fetcher, replier=replier)
        except Exception:
            # Last-resort guard: a job blowing up here must not kill the batch.
            log.warning("worker_job_crashed", job_id=str(job.id), exc_info=True)
            with contextlib.suppress(Exception):
                async with session_scope() as db:
                    await jobs.mark_failed_or_retry(
                        db,
                        job.id,
                        error="unhandled worker exception",
                        backoff_s=cfg.retry_backoff_s,
                    )
    return len(claimed)


async def run_loop(
    cfg: WorkerConfig,
    *,
    fetcher: MediaFetcher,
    replier: Replier,
    stop: asyncio.Event | None = None,
) -> None:
    """Poll until ``stop`` is set (or forever). Sleeps when the queue is empty."""
    log.info("worker_loop_start", batch_size=cfg.batch_size)
    while stop is None or not stop.is_set():
        handled = await run_once(cfg, fetcher=fetcher, replier=replier)
        if handled == 0:
            await asyncio.sleep(cfg.poll_interval_s)


async def _handle_job(
    cfg: WorkerConfig,
    job: ClaimedJob,
    *,
    fetcher: MediaFetcher,
    replier: Replier,
) -> None:
    if not job.media_id:
        async with session_scope() as db:
            await jobs.mark_failed_or_retry(
                db, job.id, error="no media_id on job", backoff_s=0
            )
        return

    # 1. Download the media (authenticated for the real Cloud API).
    media_path = await fetcher.fetch(media_id=job.media_id, dest_dir=cfg.media_dir)
    async with session_scope() as db:
        await jobs.set_media_path(db, job.id, media_path)

    # 2. Heavy CPU work off the event loop.
    try:
        result: CaptureResult = await asyncio.to_thread(
            process_capture, media_path, language=job.language
        )
    finally:
        if cfg.purge_media_on_done:
            _purge(media_path)

    # 3. Persist + decide reply based on outcome.
    final_status = await _persist_outcome(cfg, job, result)

    # 4. Reply to the user (suppressed on a retry — see _persist_outcome).
    if job.wa_phone and final_status is not None:
        with contextlib.suppress(Exception):
            await replier.send_text(to=job.wa_phone, text=result.reply_text)


async def _persist_outcome(
    cfg: WorkerConfig, job: ClaimedJob, result: CaptureResult
) -> JobStatus | None:
    """Write the terminal job row. Returns the status whose reply should be
    sent, or ``None`` if the job was re-queued for retry (send nothing yet)."""
    if result.outcome is CaptureOutcome.SUCCEEDED:
        assessment_id = await _persist_assessment(job, result)
        payload = {
            "vitals": result.vitals,
            "reply_text": result.reply_text,
            "warnings": result.warnings,
        }
        if assessment_id:
            payload["assessment_id"] = str(assessment_id)
        async with session_scope() as db:
            await jobs.mark_succeeded(db, job.id, result=payload)
        return JobStatus.SUCCEEDED

    if result.outcome is CaptureOutcome.REJECTED:
        async with session_scope() as db:
            await jobs.mark_rejected(
                db,
                job.id,
                result={"reply_text": result.reply_text, "warnings": result.warnings},
            )
        return JobStatus.REJECTED

    # FAILED → retry-or-fail. Only surface the error message once terminal.
    async with session_scope() as db:
        status = await jobs.mark_failed_or_retry(
            db, job.id, error="capture processing failed", backoff_s=cfg.retry_backoff_s
        )
    return JobStatus.FAILED if status is JobStatus.FAILED else None


async def _persist_assessment(
    job: ClaimedJob, result: CaptureResult
) -> uuid.UUID | None:
    """Persist a ToiAssessment via the existing service when a participant user
    is attached — reusing its persistence + audit trail so a WhatsApp capture
    lands in the clinician app identically to a browser capture."""
    if job.user_id is None or result.assessment_payload is None:
        return None
    try:
        async with session_scope() as db:
            user = await db.get(User, job.user_id)
            if user is None:
                return None
            payload = ToiAssessmentRequest(**result.assessment_payload)
            response = await assess_toi(
                db,
                user=user,
                payload=payload,
                ip_address=None,
                user_agent="whatsapp-worker",
            )
            return response.id
    except Exception:
        log.warning(
            "worker_assessment_persist_failed", job_id=str(job.id), exc_info=True
        )
        return None


def _purge(path: str) -> None:
    """Delete the raw video — data minimisation (plan §6.4: video ≤ extraction)."""
    with contextlib.suppress(FileNotFoundError):
        Path(path).unlink()
