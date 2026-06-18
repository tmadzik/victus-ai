"""Integration: a fake Meta inbound payload driven through the live webhook
router, end-to-end, until a ``ProcessingJob`` is queued for the worker.

Runs against the real app + real Postgres (see conftest). No signature is
required because the test environment sets no ``WHATSAPP_APP_SECRET``
(``require_signature`` is False). Each test uses a unique phone number so the
session/jobs rows are isolated without truncating tables.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from victus_api.db.models import JobStatus, ProcessingJob, WhatsAppSession

pytestmark = pytest.mark.integration

WEBHOOK = "/whatsapp/webhook"


def _unique_phone() -> str:
    # 263 (Zimbabwe) + 9 pseudo-random digits, unique per test.
    return "263" + str(uuid.uuid4().int)[:9]


def _text_payload(phone: str, body: str) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [
                                {"wa_id": phone, "profile": {"name": "Test User"}}
                            ],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": f"wamid.{uuid.uuid4().hex}",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def _video_payload(phone: str, media_id: str) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": phone,
                                    "id": f"wamid.{uuid.uuid4().hex}",
                                    "type": "video",
                                    "video": {"id": media_id},
                                }
                            ]
                        }
                    }
                ]
            }
        ],
    }


def _send_text(client: Any, phone: str, body: str) -> None:
    resp = client.post(WEBHOOK, json=_text_payload(phone, body))
    assert resp.status_code == 200, resp.text


def _send_video(client: Any, phone: str, media_id: str) -> None:
    resp = client.post(WEBHOOK, json=_video_payload(phone, media_id))
    assert resp.status_code == 200, resp.text


async def _query(phone: str) -> tuple[list[ProcessingJob], WhatsAppSession | None]:
    """Read jobs + session via a fresh engine in this loop (avoids reusing the
    app's pooled asyncpg connections across event loops)."""
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            jobs = list(
                (
                    await s.execute(
                        select(ProcessingJob).where(ProcessingJob.wa_phone == phone)
                    )
                ).scalars()
            )
            session = (
                await s.execute(
                    select(WhatsAppSession).where(WhatsAppSession.phone == phone)
                )
            ).scalar_one_or_none()
            # Detach so attributes are usable after the session closes.
            for j in jobs:
                s.expunge(j)
            if session is not None:
                s.expunge(session)
            return jobs, session
    finally:
        await engine.dispose()


async def _query_job_by_id(job_id: uuid.UUID) -> ProcessingJob | None:
    """Fetch a job by id — needed after a scrub nulls ``wa_phone``."""
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            job = await s.get(ProcessingJob, job_id)
            if job is not None:
                s.expunge(job)
            return job
    finally:
        await engine.dispose()


# --- GET verification handshake ----------------------------------------------


def test_webhook_verification_handshake(client: Any) -> None:
    # The test env sets no verify token, so the expected token is "".
    resp = client.get(
        WEBHOOK,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "",
            "hub.challenge": "challenge-123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge-123"


def test_webhook_verification_rejects_bad_token(client: Any) -> None:
    resp = client.get(
        WEBHOOK,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "nope",
        },
    )
    assert resp.status_code == 403


# --- full inbound walk → queued job ------------------------------------------


def test_full_conversation_enqueues_capture(client: Any) -> None:
    phone = _unique_phone()
    media_id = f"MEDIA-{uuid.uuid4().hex[:8]}"

    # Walk the conversation one inbound message at a time.
    _send_text(client, phone, "1")    # language: English
    _send_text(client, phone, "yes")  # consent
    _send_text(client, phone, "42")   # age
    _send_text(client, phone, "2")    # sex: Female
    _send_text(client, phone, "170")  # height cm
    _send_text(client, phone, "72")   # weight kg
    _send_text(client, phone, "88")   # waist cm
    _send_text(client, phone, "yes")  # audit Q1 (a safety trigger)
    for _ in range(5):                # audit Q2–Q6
        _send_text(client, phone, "no")

    # No job should exist until the video arrives.
    jobs, session = asyncio.run(_query(phone))
    assert jobs == []
    assert session is not None and session.state == "VIDEO"

    # The video closes the loop and enqueues a job.
    _send_video(client, phone, media_id)

    jobs, session = asyncio.run(_query(phone))
    assert len(jobs) == 1, "exactly one capture job should be queued"
    job = jobs[0]
    assert job.status == JobStatus.QUEUED
    assert job.media_id == media_id
    assert job.wa_phone == phone
    assert job.channel == "WHATSAPP"
    assert job.language == "en"
    # Intake captured from the conversation maps to the triage contract.
    assert job.intake["inputs"] == {
        "age_years": 42,
        "sex": "FEMALE",
        "height_cm": 170,
        "weight_kg": 72,
        "waist_cm": 88,
    }
    assert "polydipsia_unquenchable_thirst" in job.intake["symptoms"]["safety_triggers"]
    assert session is not None and session.state == "COMPLETE"


def test_duplicate_message_is_idempotent(client: Any) -> None:
    phone = _unique_phone()
    # Re-deliver the identical first message twice (same wamid).
    payload = _text_payload(phone, "1")
    assert client.post(WEBHOOK, json=payload).status_code == 200
    assert client.post(WEBHOOK, json=payload).status_code == 200

    _, session = asyncio.run(_query(phone))
    # The duplicate must not double-advance: still awaiting consent after lang.
    assert session is not None
    assert session.state == "CONSENT"


def test_stop_command_erases_session_and_scrubs_jobs(client: Any) -> None:
    """The STOP command must honour 'reply STOP to delete your information':
    delete the session row and strip PII from the phone's jobs."""
    phone = _unique_phone()
    media_id = f"MEDIA-{uuid.uuid4().hex[:8]}"

    _send_text(client, phone, "1")
    _send_text(client, phone, "yes")
    _send_text(client, phone, "42")
    _send_text(client, phone, "2")
    _send_text(client, phone, "170")
    _send_text(client, phone, "72")
    _send_text(client, phone, "88")
    _send_text(client, phone, "yes")
    for _ in range(5):
        _send_text(client, phone, "no")
    _send_video(client, phone, media_id)

    jobs, session = asyncio.run(_query(phone))
    assert len(jobs) == 1 and session is not None
    job_id = jobs[0].id

    # The user asks to delete everything.
    _send_text(client, phone, "STOP")

    jobs_by_phone, session_after = asyncio.run(_query(phone))
    assert session_after is None, "session row must be deleted on STOP"
    assert jobs_by_phone == [], "no job may still reference the phone"

    # The job row is retained for the audit trail but holds no PII, and the
    # not-yet-run capture is cancelled.
    job = asyncio.run(_query_job_by_id(job_id))
    assert job is not None
    assert job.status == JobStatus.REJECTED
    assert job.wa_phone is None
    assert job.media_id is None
    assert job.intake == {}
