"""Integration: care-navigation referrals.

Covers role gating (a patient cannot raise a referral), creation by a clinician,
the participant seeing their own referral via /me, the status lifecycle, and a
404 on an unknown referral — against the live app + real Postgres.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import register, unread_count
from victus_api.db.models import User, UserRole

pytestmark = pytest.mark.integration


async def _promote(email: str, role: UserRole) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            await s.execute(
                update(User)
                .where(func.lower(User.email) == email.lower())
                .values(role=role)
            )
            await s.commit()
    finally:
        await engine.dispose()


def _clinician(client: Any) -> dict[str, Any]:
    c = register(client, "PATIENT")
    asyncio.run(_promote(c["email"], UserRole.CLINICIAN))
    return c


def _referral_payload(participant_id: str) -> dict[str, Any]:
    return {
        "participant_user_id": participant_id,
        "destination_type": "VICTUS_FACILITY",
        "destination_name": "Victus Wellness — Harare",
        "reason": "Stage-2 hypertension flagged on Pathway A.",
        "urgency": "URGENT",
    }


def test_patient_cannot_raise_referral(client: Any) -> None:
    patient = register(client, "PATIENT")
    r = client.post(
        "/referrals", headers=patient["headers"], json=_referral_payload(patient["id"])
    )
    assert r.status_code == 403, r.text


def test_clinician_creates_and_participant_sees_it(client: Any) -> None:
    participant = register(client, "PATIENT")
    clinician = _clinician(client)

    before = unread_count(client, participant["headers"])
    created = client.post(
        "/referrals",
        headers=clinician["headers"],
        json=_referral_payload(participant["id"]),
    )
    assert created.status_code == 201, created.text
    ref = created.json()

    # The participant is notified of the new referral.
    assert unread_count(client, participant["headers"]) == before + 1
    assert ref["status"] == "PENDING"
    assert ref["urgency"] == "URGENT"
    assert ref["created_by_user_id"] == clinician["id"]

    # The participant sees their own referral.
    mine = client.get("/referrals/me", headers=participant["headers"])
    assert mine.status_code == 200, mine.text
    assert any(x["id"] == ref["id"] for x in mine.json())

    # The clinician can list it under the participant.
    plist = client.get(
        f"/referrals/participant/{participant['id']}", headers=clinician["headers"]
    )
    assert plist.status_code == 200
    assert any(x["id"] == ref["id"] for x in plist.json())

    # Status lifecycle.
    upd = client.patch(
        f"/referrals/{ref['id']}/status",
        headers=clinician["headers"],
        json={"status": "ACKNOWLEDGED", "notes": "Facility contacted."},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["status"] == "ACKNOWLEDGED"
    assert upd.json()["notes"] == "Facility contacted."


def test_status_update_unknown_referral_is_404(client: Any) -> None:
    clinician = _clinician(client)
    r = client.patch(
        f"/referrals/{uuid.uuid4()}/status",
        headers=clinician["headers"],
        json={"status": "COMPLETED"},
    )
    assert r.status_code == 404, r.text


def test_record_outcome_closes_the_care_loop(client: Any) -> None:
    participant = register(client, "PATIENT")
    clinician = _clinician(client)
    created = client.post(
        "/referrals",
        headers=clinician["headers"],
        json=_referral_payload(participant["id"]),
    )
    assert created.status_code == 201, created.text
    ref = created.json()
    # A fresh referral starts with no facility outcome.
    assert ref["outcome"] == "PENDING"
    assert ref["outcome_recorded_at"] is None

    upd = client.patch(
        f"/referrals/{ref['id']}/outcome",
        headers=clinician["headers"],
        json={"outcome": "ATTENDED_CONFIRMED", "notes": "HbA1c 7.4% — confirmed."},
    )
    assert upd.status_code == 200, upd.text
    body = upd.json()
    assert body["outcome"] == "ATTENDED_CONFIRMED"
    assert body["outcome_recorded_at"] is not None
    assert body["outcome_notes"] == "HbA1c 7.4% — confirmed."


def test_patient_cannot_record_outcome(client: Any) -> None:
    participant = register(client, "PATIENT")
    clinician = _clinician(client)
    ref = client.post(
        "/referrals",
        headers=clinician["headers"],
        json=_referral_payload(participant["id"]),
    ).json()
    r = client.patch(
        f"/referrals/{ref['id']}/outcome",
        headers=participant["headers"],
        json={"outcome": "ATTENDED_CONFIRMED"},
    )
    assert r.status_code == 403, r.text


def test_outcome_unknown_referral_is_404(client: Any) -> None:
    clinician = _clinician(client)
    r = client.patch(
        f"/referrals/{uuid.uuid4()}/outcome",
        headers=clinician["headers"],
        json={"outcome": "DID_NOT_ATTEND"},
    )
    assert r.status_code == 404, r.text
