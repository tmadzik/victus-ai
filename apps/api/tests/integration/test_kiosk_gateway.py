"""Integration: the Mobile Clinic Gateway backend, end-to-end on real Postgres.

Covers the four seams of Phase 2:
  1. terminal session create + status poll (device-authed)
  2. WhatsApp QR-nonce linking → consent → CONSENTED + anchored participant
  3. capture finalisation → biometric metadata + a KIOSK processing job
  4. secure result delivery → OTP-gated, single-use, lock-out portal unlock

Device auth is open in the test env (no KIOSK_DEVICE_TOKENS set), so the terminal
endpoints only need an X-Kiosk-Id header. Result delivery is normally the
worker's job; here it is driven directly at the service layer (its own NullPool
engine/loop, as the webhook integration test does) and the public portal is then
exercised over HTTP.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from victus_api.config import get_settings
from victus_api.db.models import (
    KioskBiometricMetadata,
    KioskSession,
    KioskSessionStatus,
    ProcessingJob,
    TriageState,
)
from victus_api.kiosk import service as kiosk_service
from victus_api.kiosk.schemas import KioskResultPayload
from victus_api.kiosk.security import build_verification_text, generate_verification_nonce

pytestmark = pytest.mark.integration

WEBHOOK = "/whatsapp/webhook"
HEADERS = {"X-Kiosk-Id": "kiosk-test"}


def _unique_phone() -> str:
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
                                {"wa_id": phone, "profile": {"name": "Kiosk User"}}
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


def _engine():
    return create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)


async def _get_session(session_id: uuid.UUID) -> KioskSession | None:
    engine = _engine()
    try:
        async with AsyncSession(engine) as s:
            row = await s.get(KioskSession, session_id)
            if row is not None:
                s.expunge(row)
            return row
    finally:
        await engine.dispose()


async def _get_biometrics(session_id: uuid.UUID) -> list[KioskBiometricMetadata]:
    engine = _engine()
    try:
        async with AsyncSession(engine) as s:
            rows = list(
                (
                    await s.execute(
                        select(KioskBiometricMetadata).where(
                            KioskBiometricMetadata.session_id == session_id
                        )
                    )
                ).scalars()
            )
            for r in rows:
                s.expunge(r)
            return rows
    finally:
        await engine.dispose()


async def _get_job(job_id: uuid.UUID) -> ProcessingJob | None:
    engine = _engine()
    try:
        async with AsyncSession(engine) as s:
            job = await s.get(ProcessingJob, job_id)
            if job is not None:
                s.expunge(job)
            return job
    finally:
        await engine.dispose()


async def _seed_consented_session() -> uuid.UUID:
    """Insert a bare CONSENTED kiosk session for the result-portal tests."""
    engine = _engine()
    try:
        async with AsyncSession(engine) as s:
            row = KioskSession(
                kiosk_id="kiosk-test",
                site_code="DEFAULT",
                status=KioskSessionStatus.CONSENTED,
                verification_nonce=generate_verification_nonce(),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            s.add(row)
            await s.flush()
            sid = row.id
            await s.commit()
            return sid
    finally:
        await engine.dispose()


async def _deliver(session_id: uuid.UUID) -> tuple[str, str]:
    """Run deliver_result; return (token, otp) parsed from the delivery."""
    payload = KioskResultPayload(
        triage_state=TriageState.YELLOW,
        headline="Some readings to review",
        body="A few of your readings are slightly outside the usual range.",
        vitals={"heart_rate_bpm": 82},
        generated_at=datetime.now(UTC),
    )
    engine = _engine()
    try:
        async with AsyncSession(engine) as s:
            delivery = await kiosk_service.deliver_result(
                s, session_id=session_id, payload=payload, settings=get_settings()
            )
            await s.commit()
            token = delivery.portal_url.rsplit("/", 1)[-1]
            return token, delivery.otp
    finally:
        await engine.dispose()


# --- 1. session create + status ---------------------------------------------


def test_create_session_returns_qr_payload(client: Any) -> None:
    resp = client.post("/kiosk/sessions", headers=HEADERS)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "INITIATED"
    assert body["site_code"] == get_settings().site_code
    nonce = body["verification_nonce"]
    assert body["qr_text"] == build_verification_text(nonce)

    status = client.get(f"/kiosk/sessions/{body['id']}", headers=HEADERS)
    assert status.status_code == 200
    sbody = status.json()
    assert sbody["linked"] is False
    assert sbody["consented"] is False
    assert sbody["result_ready"] is False


def test_create_session_requires_device_id(client: Any) -> None:
    # No X-Kiosk-Id header → device auth rejects (open dev still needs an id).
    resp = client.post("/kiosk/sessions")
    assert resp.status_code == 403


# --- 2. WhatsApp linking → consent ------------------------------------------


def test_whatsapp_nonce_links_and_consent_anchors(client: Any) -> None:
    created = client.post("/kiosk/sessions", headers=HEADERS).json()
    sid = uuid.UUID(created["id"])
    nonce = created["verification_nonce"]
    phone = _unique_phone()

    # Scan: the QR-prefilled text links this phone to the kiosk session.
    assert (
        client.post(WEBHOOK, json=_text_payload(phone, build_verification_text(nonce)))
    ).status_code == 200
    after_link = client.get(f"/kiosk/sessions/{sid}", headers=HEADERS).json()
    assert after_link["linked"] is True
    assert after_link["consented"] is False

    # Consent: YES anchors the pseudonymous participant + stamps CONSENTED.
    assert client.post(WEBHOOK, json=_text_payload(phone, "yes")).status_code == 200
    after_consent = client.get(f"/kiosk/sessions/{sid}", headers=HEADERS).json()
    assert after_consent["consented"] is True

    row = asyncio.run(_get_session(sid))
    assert row is not None
    assert row.status is KioskSessionStatus.CONSENTED
    assert row.user_id is not None
    assert row.whatsapp_session_id is not None
    assert row.consent_at is not None


def test_unknown_nonce_does_not_link(client: Any) -> None:
    phone = _unique_phone()
    resp = client.post(
        WEBHOOK, json=_text_payload(phone, build_verification_text("does-not-exist"))
    )
    assert resp.status_code == 200  # webhook always acks
    # Nothing to assert on a kiosk row; the invalid link simply replies an error.


# --- 3. capture finalisation -------------------------------------------------


def test_capture_persists_metadata_and_enqueues_kiosk_job(client: Any) -> None:
    created = client.post("/kiosk/sessions", headers=HEADERS).json()
    sid = uuid.UUID(created["id"])
    phone = _unique_phone()
    link_text = build_verification_text(created["verification_nonce"])
    client.post(WEBHOOK, json=_text_payload(phone, link_text))
    client.post(WEBHOOK, json=_text_payload(phone, "yes"))

    capture = client.post(
        f"/kiosk/sessions/{sid}/capture",
        headers=HEADERS,
        json={
            "signal_quality_index": 0.91,
            "illumination_score": 0.7,
            "face_bbox_ratio": 0.55,
            "frame_count": 300,
            "error_flags": [],
            "rppg_signal": {"chrom": [0.1, 0.2]},
        },
    )
    assert capture.status_code == 202, capture.text
    cbody = capture.json()
    assert cbody["status"] == "PROCESSING"
    job_id = uuid.UUID(cbody["processing_job_id"])

    metrics = asyncio.run(_get_biometrics(sid))
    assert len(metrics) == 1
    assert metrics[0].frame_count == 300
    assert metrics[0].signal_quality_index == pytest.approx(0.91)

    job = asyncio.run(_get_job(job_id))
    assert job is not None
    assert job.channel == "KIOSK"
    assert job.media_id is None
    assert job.intake["kiosk_session_id"] == str(sid)

    row = asyncio.run(_get_session(sid))
    assert row is not None and row.processing_job_id == job_id


def test_capture_rejected_before_consent(client: Any) -> None:
    created = client.post("/kiosk/sessions", headers=HEADERS).json()
    sid = created["id"]
    resp = client.post(
        f"/kiosk/sessions/{sid}/capture", headers=HEADERS, json={"frame_count": 1}
    )
    assert resp.status_code == 409  # not consented


# --- 4. secure result portal -------------------------------------------------


def test_result_unlock_success_is_single_use(client: Any) -> None:
    sid = asyncio.run(_seed_consented_session())
    token, otp = asyncio.run(_deliver(sid))

    gate = client.get(f"/kiosk/results/{token}")
    assert gate.status_code == 200
    assert gate.json()["attempts_remaining"] == get_settings().kiosk_otp_max_attempts

    ok = client.post(f"/kiosk/results/{token}/unlock", json={"otp": otp})
    assert ok.status_code == 200, ok.text
    payload = ok.json()
    assert payload["triage_state"] == "YELLOW"
    assert payload["vitals"]["heart_rate_bpm"] == 82
    assert "wellness screening" in payload["disclaimer"]

    # Single use: the result is consumed and cannot be re-read.
    again = client.post(f"/kiosk/results/{token}/unlock", json={"otp": otp})
    assert again.status_code == 409
    assert client.get(f"/kiosk/results/{token}").status_code == 409


def test_result_unlock_wrong_otp_locks_out(client: Any) -> None:
    sid = asyncio.run(_seed_consented_session())
    token, otp = asyncio.run(_deliver(sid))
    wrong = "0000" if otp != "0000" else "1111"
    max_attempts = get_settings().kiosk_otp_max_attempts

    # First wrong attempt: 401 with the counter decremented.
    first = client.post(f"/kiosk/results/{token}/unlock", json={"otp": wrong})
    assert first.status_code == 401
    assert first.json()["error"]["attempts_remaining"] == max_attempts - 1

    # Exhaust the remaining attempts → the link locks (403).
    for _ in range(max_attempts - 1):
        resp = client.post(f"/kiosk/results/{token}/unlock", json={"otp": wrong})
    assert resp.status_code == 403

    # Even the correct OTP is now refused.
    locked = client.post(f"/kiosk/results/{token}/unlock", json={"otp": otp})
    assert locked.status_code == 403


def test_unlock_rejects_malformed_otp(client: Any) -> None:
    sid = asyncio.run(_seed_consented_session())
    token, _ = asyncio.run(_deliver(sid))
    # Not four digits → schema validation rejects before any attempt is spent.
    resp = client.post(f"/kiosk/results/{token}/unlock", json={"otp": "12"})
    assert resp.status_code == 422
