"""Integration: the kiosk capture worker, reapers, and erasure cascade.

Drives ``run_kiosk_once`` against the real pipeline + Postgres: a seeded KIOSK
job with synthetic rPPG frames is turned into a sealed result, the secure-portal
link + OTP are "sent" (captured by an InMemoryReplier), and the round-trip is
proven by unlocking the result. Also covers the re-record path, the expiry/
spent-result reapers, and the kiosk-data cascade used by account erasure.
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from victus_api.config import get_settings
from victus_api.db.models import (
    JobStatus,
    KioskBiometricMetadata,
    KioskClinicalResult,
    KioskResultToken,
    KioskSession,
    KioskSessionStatus,
    ProcessingJob,
    User,
    UserRole,
    WhatsAppSession,
)
from victus_api.kiosk import service as kiosk_service
from victus_api.worker.config import WorkerConfig
from victus_api.worker.kiosk_runner import run_kiosk_once
from victus_api.worker.reply import InMemoryReplier

pytestmark = pytest.mark.integration


def _engine():
    return create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)


def _frames(n: int = 900, fps: int = 30) -> list[dict[str, float]]:
    """A clean green-dominant pulsatile + respiratory trace (high-SNR demo)."""
    out: list[dict[str, float]] = []
    for i in range(n):
        t = i / fps
        pulse = math.sin(2 * math.pi * (66 / 60) * t)
        resp = math.sin(2 * math.pi * (15 / 60) * t)
        out.append(
            {
                "t_ms": round(i * 1000 / fps),
                "r": 180 + 0.4 * pulse + 0.8 * resp,
                "g": 120 + 2.2 * pulse + 0.5 * resp,
                "b": 110 + 0.9 * pulse + 0.4 * resp,
            }
        )
    return out


async def _seed(
    *, frames: list[dict[str, float]], with_user: bool = True
) -> tuple[uuid.UUID, uuid.UUID, str]:
    """Seed a CONSENTED kiosk session + linked WhatsApp session + KIOSK job.

    Returns ``(session_id, job_id, phone)``.
    """
    phone = "263" + uuid.uuid4().int.__str__()[:9]
    engine = _engine()
    try:
        async with AsyncSession(engine) as db:
            user_id: uuid.UUID | None = None
            if with_user:
                user = User(role=UserRole.PATIENT, is_active=True, site_code="DEFAULT")
                db.add(user)
                await db.flush()
                user_id = user.id
            wa = WhatsAppSession(phone=phone, state="COMPLETE", user_id=user_id)
            db.add(wa)
            await db.flush()
            session = KioskSession(
                kiosk_id="kiosk-test",
                site_code="DEFAULT",
                status=KioskSessionStatus.CONSENTED,
                verification_nonce=uuid.uuid4().hex,
                user_id=user_id,
                whatsapp_session_id=wa.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(session)
            await db.flush()
            job = ProcessingJob(
                status=JobStatus.QUEUED,
                channel="KIOSK",
                user_id=user_id,
                intake={
                    "kiosk_session_id": str(session.id),
                    "rppg_signal": {
                        "frames": frames,
                        "sample_rate_hz": 30.0,
                        "duration_s": 30.0,
                    },
                },
            )
            db.add(job)
            await db.flush()
            session.processing_job_id = job.id
            ids = (session.id, job.id, phone)
            await db.commit()
            return ids
    finally:
        await engine.dispose()


async def _fetch_job_session(
    job_id: uuid.UUID, session_id: uuid.UUID
) -> tuple[ProcessingJob | None, KioskSession | None]:
    engine = _engine()
    try:
        async with AsyncSession(engine) as db:
            job = await db.get(ProcessingJob, job_id)
            session = await db.get(KioskSession, session_id)
            if job is not None:
                db.expunge(job)
            if session is not None:
                db.expunge(session)
            return job, session
    finally:
        await engine.dispose()


def _cfg() -> WorkerConfig:
    return WorkerConfig.from_env()


# --- worker happy path ------------------------------------------------------


def test_kiosk_worker_delivers_and_unlocks(client: object) -> None:
    session_id, job_id, phone = asyncio.run(_seed(frames=_frames()))
    replier = InMemoryReplier()

    handled = asyncio.run(run_kiosk_once(_cfg(), replier=replier))
    assert handled >= 1

    job, session = asyncio.run(_fetch_job_session(job_id, session_id))
    assert job is not None and job.status == JobStatus.SUCCEEDED
    assert session is not None and session.status == KioskSessionStatus.COMPLETE

    # Two messages to the participant: the portal link, then the OTP.
    sent_to_phone = [text for to, text in replier.sent if to == phone]
    assert len(sent_to_phone) == 2
    link_msg, otp_msg = sent_to_phone
    assert '/v/' in link_msg

    # End-to-end: extract the token + OTP and unlock the sealed result.
    token = link_msg.split('/v/')[1].split()[0]
    otp_match = re.search(r'\*(\d{4})\*', otp_msg)
    assert otp_match is not None
    otp = otp_match.group(1)

    async def _unlock() -> object:
        engine = _engine()
        try:
            async with AsyncSession(engine) as db:
                return await kiosk_service.unlock_result(
                    db, token=token, otp=otp, settings=get_settings()
                )
        finally:
            await engine.dispose()

    result = asyncio.run(_unlock())
    assert isinstance(result, kiosk_service.UnlockSuccess)
    assert result.payload.headline == 'Your wellness check-up is ready'
    assert 'not a medical diagnosis' in result.payload.body


def test_kiosk_worker_rejects_short_capture(client: object) -> None:
    # Fewer than MIN_FRAMES → ToiAssessmentRequest validation fails → re-record.
    session_id, job_id, phone = asyncio.run(_seed(frames=_frames(n=40)))
    replier = InMemoryReplier()

    asyncio.run(run_kiosk_once(_cfg(), replier=replier))

    job, session = asyncio.run(_fetch_job_session(job_id, session_id))
    assert job is not None and job.status == JobStatus.REJECTED
    assert session is not None and session.status == KioskSessionStatus.ABORTED
    sent_to_phone = [text for to, text in replier.sent if to == phone]
    assert len(sent_to_phone) == 1
    assert 'try the wellness check-up again' in sent_to_phone[0]


# --- reapers ----------------------------------------------------------------


def test_expire_stale_sessions(client: object) -> None:
    async def _run() -> KioskSessionStatus:
        engine = _engine()
        try:
            async with AsyncSession(engine) as db:
                row = KioskSession(
                    kiosk_id='kiosk-test',
                    site_code='DEFAULT',
                    status=KioskSessionStatus.INITIATED,
                    verification_nonce=uuid.uuid4().hex,
                    expires_at=datetime.now(UTC) - timedelta(minutes=1),
                )
                db.add(row)
                await db.flush()
                sid = row.id
                await db.commit()
            async with AsyncSession(engine) as db:
                await kiosk_service.expire_stale_sessions(db)
                await db.commit()
            async with AsyncSession(engine) as db:
                refreshed = await db.get(KioskSession, sid)
                assert refreshed is not None
                return refreshed.status
        finally:
            await engine.dispose()

    assert asyncio.run(_run()) is KioskSessionStatus.EXPIRED


def test_purge_spent_results_drops_consumed_payload(client: object) -> None:
    session_id, _job_id, _phone = asyncio.run(_seed(frames=_frames()))

    async def _run() -> int:
        engine = _engine()
        try:
            # Seal a result, then mark its token consumed → it becomes spent.
            async with AsyncSession(engine) as db:
                payload = kiosk_service.KioskResultPayload(
                    headline='h',
                    body='b',
                    generated_at=datetime.now(UTC),
                )
                await kiosk_service.deliver_result(
                    db, session_id=session_id, payload=payload, settings=get_settings()
                )
                await db.commit()
            async with AsyncSession(engine) as db:
                tok = (
                    await db.execute(
                        select(KioskResultToken).where(
                            KioskResultToken.session_id == session_id
                        )
                    )
                ).scalar_one()
                tok.consumed_at = datetime.now(UTC)
                await db.commit()
            async with AsyncSession(engine) as db:
                purged = await kiosk_service.purge_spent_results(db)
                await db.commit()
            async with AsyncSession(engine) as db:
                remaining = (
                    await db.execute(
                        select(KioskClinicalResult).where(
                            KioskClinicalResult.session_id == session_id
                        )
                    )
                ).scalars().all()
                assert remaining == []
            return purged
        finally:
            await engine.dispose()

    assert asyncio.run(_run()) >= 1


# --- erasure cascade --------------------------------------------------------


def test_purge_for_whatsapp_session_cascades(client: object) -> None:
    session_id, _job_id, _phone = asyncio.run(_seed(frames=_frames()))

    async def _run() -> tuple[int, int]:
        engine = _engine()
        try:
            # Give the session a result + token + biometric row to cascade.
            async with AsyncSession(engine) as db:
                db.add(
                    KioskBiometricMetadata(session_id=session_id, frame_count=900)
                )
                payload = kiosk_service.KioskResultPayload(
                    headline='h', body='b', generated_at=datetime.now(UTC)
                )
                await kiosk_service.deliver_result(
                    db, session_id=session_id, payload=payload, settings=get_settings()
                )
                await db.commit()
            async with AsyncSession(engine) as db:
                session = await db.get(KioskSession, session_id)
                assert session is not None and session.whatsapp_session_id is not None
                deleted = await kiosk_service.purge_for_whatsapp_session(
                    db, whatsapp_session_id=session.whatsapp_session_id
                )
                await db.commit()
            async with AsyncSession(engine) as db:
                tokens = (
                    await db.execute(
                        select(KioskResultToken).where(
                            KioskResultToken.session_id == session_id
                        )
                    )
                ).scalars().all()
                results = (
                    await db.execute(
                        select(KioskClinicalResult).where(
                            KioskClinicalResult.session_id == session_id
                        )
                    )
                ).scalars().all()
                gone = await db.get(KioskSession, session_id)
                assert gone is None
                assert tokens == [] and results == []
            return deleted, 0
        finally:
            await engine.dispose()

    deleted, _ = asyncio.run(_run())
    assert deleted == 1
