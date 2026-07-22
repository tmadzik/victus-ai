"""Kiosk capture worker: claim KIOSK jobs → vitals → secure result delivery.

The kiosk terminal already extracted the rPPG traces in-browser (no raw frames),
so unlike the WhatsApp rail there is no media to download — the derived signal
rides in ``job.intake['rppg_signal']``. This runner turns that into vitals via
the shared TOI pipeline, seals the summary + mints the single-use OTP token
(``kiosk_service.deliver_result``), and sends the participant their secure-portal
link and access code over WhatsApp.

Reapers run each cycle (cheap, idempotent): abandoned pre-capture sessions are
expired and spent encrypted results are dropped. Structured logs carry only ids
— never the phone, OTP, or any health value.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError

from victus_api.config import Settings, get_settings
from victus_api.core.logging import get_logger
from victus_api.db.models import KioskSession, User, WhatsAppSession
from victus_api.db.session import session_scope
from victus_api.kiosk import service as kiosk_service
from victus_api.kiosk.schemas import KioskResultPayload
from victus_api.toi.schemas import ToiAssessmentRequest, ToiAssessmentResponse
from victus_api.toi.service import assess_toi
from victus_api.worker import jobs
from victus_api.worker.config import WorkerConfig
from victus_api.worker.jobs import ClaimedJob
from victus_api.worker.reply import Replier

log = get_logger(__name__)

# Participant-facing vitals surfaced on the portal: biomarker key → (label,
# validated). Only the camera-derived signals the pipeline actually computes
# appear here — there is no cuffless blood pressure and no cardiovascular-risk
# score in Pathway B, so neither can be shown.
#
# The unvalidated ones are labelled as such on screen and only reach the payload
# at all when TOI_EXPOSE_EXPERIMENTAL_BIOMARKERS=1 (research/demo builds); the
# default gate strips them upstream in the TOI service.
_VITAL_LABELS: dict[str, tuple[str, bool]] = {
    "heart_rate": ("Heart rate", True),
    "respiratory_rate": ("Breathing rate", True),
    "hrv_rmssd": ("Heart-rate variability", False),
    "hrv_sdnn": ("HRV (SDNN)", False),
    "stress_index": ("Stress index", False),
}

_QUALITY_NOTE: dict[str, str] = {
    "GOOD": "We got a clear reading.",
    "DEGRADED": "The reading was a little noisy, so treat these as rough estimates.",
    "POOR": "The signal was weak, so these are rough estimates only.",
}

_RETRY_MESSAGE = (
    "We couldn't get a clear reading this time. Please return to the kiosk and "
    "try the wellness check-up again."
)


def _otp_message(otp: str) -> str:
    return (
        f"Your one-time access code is *{otp}*. It works once and expires in "
        "24 hours."
    )


def build_result_payload(toi: ToiAssessmentResponse) -> KioskResultPayload:
    """Compose the non-diagnostic summary sealed for the secure portal."""
    vitals: dict[str, object] = {}
    for key, (label, validated) in _VITAL_LABELS.items():
        bm = toi.biomarkers.get(key)
        if bm is not None and bm.value is not None:
            unit = (bm.unit or "").strip()
            # Never let an unvalidated estimate read like a measurement.
            shown = label if validated else f"{label} (experimental)"
            vitals[shown] = f"{round(bm.value, 1)} {unit}".strip()

    # Provenance: which chrominance method won on SNR for this capture. This is
    # the part that is tuned for Fitzpatrick III–VI, so it is worth surfacing.
    method = (toi.signal_quality.method_selected or "").upper()
    if method in ("CHROM", "POS"):
        vitals["Method"] = f"{method} (auto-selected)"

    note = _QUALITY_NOTE.get(toi.quality.value, "")
    body = (
        f"{note} Please share these readings with a health worker. This is a "
        "wellness screening, not a medical diagnosis."
    ).strip()
    return KioskResultPayload(
        triage_state=None,
        headline="Your wellness check-up is ready",
        body=body,
        vitals=vitals,
        generated_at=datetime.now(UTC),
    )


async def run_kiosk_once(
    cfg: WorkerConfig,
    *,
    replier: Replier,
    settings: Settings | None = None,
) -> int:
    """Reap stale state, then claim + process one batch of KIOSK jobs."""
    resolved = settings or get_settings()

    async with session_scope() as db:
        expired = await kiosk_service.expire_stale_sessions(db)
        purged = await kiosk_service.purge_spent_results(db)
    if expired or purged:
        log.info("kiosk_reaper_swept", sessions_expired=expired, results_purged=purged)

    async with session_scope() as db:
        claimed = await jobs.claim_next_batch(db, limit=cfg.batch_size, channel="KIOSK")

    for job in claimed:
        try:
            await _handle_kiosk_job(job, replier=replier, settings=resolved)
        except Exception:
            log.warning("kiosk_worker_job_crashed", job_id=str(job.id), exc_info=True)
            with contextlib.suppress(Exception):
                async with session_scope() as db:
                    await jobs.mark_failed_or_retry(
                        db,
                        job.id,
                        error="unhandled kiosk worker exception",
                        backoff_s=cfg.retry_backoff_s,
                    )
    return len(claimed)


async def run_kiosk_loop(
    cfg: WorkerConfig,
    *,
    replier: Replier,
    stop: asyncio.Event | None = None,
) -> None:
    """Poll the KIOSK queue until ``stop`` is set (or forever)."""
    log.info("kiosk_worker_loop_start", batch_size=cfg.batch_size)
    while stop is None or not stop.is_set():
        handled = await run_kiosk_once(cfg, replier=replier)
        if handled == 0:
            await asyncio.sleep(cfg.poll_interval_s)


async def _handle_kiosk_job(
    job: ClaimedJob, *, replier: Replier, settings: Settings
) -> None:
    intake = job.intake or {}
    session_raw = intake.get("kiosk_session_id")
    signal = intake.get("rppg_signal") or {}
    if not session_raw:
        async with session_scope() as db:
            await jobs.mark_failed_or_retry(
                db, job.id, error="kiosk job missing session id", backoff_s=0
            )
        return
    session_id = uuid.UUID(str(session_raw))

    # Build the TOI request from the kiosk-extracted frames. A too-short or
    # malformed capture fails validation → re-record (a normal outcome).
    try:
        toi_request = ToiAssessmentRequest(
            frames=signal.get("frames", []),
            sample_rate_hz=float(signal.get("sample_rate_hz", 30.0)),
            duration_s=float(signal.get("duration_s", 30.0)),
        )
    except (ValidationError, TypeError, ValueError):
        await _reject_capture(job, session_id, replier, reason="invalid_signal")
        return

    if job.user_id is None:
        await _reject_capture(job, session_id, replier, reason="no_participant")
        return

    # Pipeline + seal + mint, atomically. The cleartext token/OTP come back for
    # out-of-band delivery; nothing sensitive is logged.
    delivery: kiosk_service.ResultDelivery | None = None
    async with session_scope() as db:
        user = await db.get(User, job.user_id)
        if user is None:
            await jobs.mark_rejected(db, job.id, result={"reason": "user_missing"})
            await kiosk_service.abort_session(db, session_id=session_id)
        else:
            toi = await assess_toi(
                db,
                user=user,
                payload=toi_request,
                ip_address=None,
                user_agent="kiosk-worker",
            )
            payload = build_result_payload(toi)
            delivery = await kiosk_service.deliver_result(
                db, session_id=session_id, payload=payload, settings=settings
            )
            await jobs.mark_succeeded(
                db,
                job.id,
                result={
                    "kiosk_session_id": str(session_id),
                    "quality": toi.quality.value,
                },
            )

    if delivery is not None and delivery.phone:
        with contextlib.suppress(Exception):
            await replier.send_text(to=delivery.phone, text=delivery.message)
            await replier.send_text(to=delivery.phone, text=_otp_message(delivery.otp))
        log.info("kiosk_result_sent", session_id=str(session_id))


async def _reject_capture(
    job: ClaimedJob,
    session_id: uuid.UUID,
    replier: Replier,
    *,
    reason: str,
) -> None:
    """Mark an unusable capture rejected, abort the session, ask to re-record."""
    phone: str | None = None
    async with session_scope() as db:
        await jobs.mark_rejected(db, job.id, result={"reason": reason})
        row = await db.get(KioskSession, session_id)
        if row is not None:
            await kiosk_service.abort_session(db, session_id=session_id)
            if row.whatsapp_session_id is not None:
                wa = await db.get(WhatsAppSession, row.whatsapp_session_id)
                phone = wa.phone if wa is not None else None
    log.info("kiosk_capture_rejected", session_id=str(session_id), reason=reason)
    if phone:
        with contextlib.suppress(Exception):
            await replier.send_text(to=phone, text=_RETRY_MESSAGE)
