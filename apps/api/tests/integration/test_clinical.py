"""Integration: clinician participant-review surface.

Covers role gating (patients refused), participant search, the identified
history view (with a seeded triage assessment), 404 on an unknown participant,
and that every access writes a CLINICIAN_PARTICIPANT_VIEWED audit entry —
against the live app + real Postgres.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import grant_consent, register
from victus_api.db.models import AuditAction, AuditLog, User, UserRole

pytestmark = pytest.mark.integration

TRIAGE_INPUTS: dict[str, Any] = {
    "age_years": 54,
    "sex": "MALE",
    "height_cm": 172,
    "weight_kg": 99,
    "waist_cm": 112,
    "systolic_bp_mmhg": 158,
    "diastolic_bp_mmhg": 98,
}


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


async def _count_view_audits(actor_id: str) -> int:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            n = await s.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.actor_id == uuid.UUID(actor_id),
                    AuditLog.action == AuditAction.CLINICIAN_PARTICIPANT_VIEWED,
                )
            )
            return int(n or 0)
    finally:
        await engine.dispose()


def _make_clinician(client: Any) -> dict[str, Any]:
    clinician = register(client, "PATIENT")
    asyncio.run(_promote(clinician["email"], UserRole.CLINICIAN))
    return clinician


def _seed_participant(client: Any) -> dict[str, Any]:
    participant = register(client, "PATIENT")
    grant_consent(client, participant["headers"], "TRIAGE")
    r = client.post(
        "/pathways/triage/assess",
        headers=participant["headers"],
        json={"inputs": TRIAGE_INPUTS, "symptoms": {"safety_triggers": [], "contextual": []}},
    )
    assert r.status_code == 200, r.text
    return participant


def _enroll(client: Any, headers: dict[str, str]) -> None:
    r = client.post(
        "/enrollment",
        headers=headers,
        json={
            "full_name": "Enrolled Participant",
            "email": f"enrolled_{uuid.uuid4().hex[:8]}@example.com",
            "patient_id": f"MRN-{uuid.uuid4().hex[:8]}",
            "age_range": "40-49",
            "biological_sex": "MALE",
            "region": "NG",
            "race_ethnicity": "Black African",
            "consent_triage": True,
            "consent_toi_imaging": True,
            "consent_research": False,
        },
    )
    assert r.status_code == 201, r.text


def test_patient_cannot_access_clinical(client: Any) -> None:
    user = register(client, "PATIENT")
    assert client.get(
        "/clinical/participants", headers=user["headers"], params={"q": "x"}
    ).status_code == 403
    rid = uuid.uuid4()
    assert client.get(
        f"/clinical/participants/{rid}/history", headers=user["headers"]
    ).status_code == 403


def test_clinician_searches_and_opens_history(client: Any) -> None:
    participant = _seed_participant(client)
    clinician = _make_clinician(client)

    # Search by an email substring unique to this participant.
    needle = participant["email"].split("@")[0]
    sr = client.get(
        "/clinical/participants", headers=clinician["headers"], params={"q": needle}
    )
    assert sr.status_code == 200, sr.text
    hits = [p for p in sr.json() if p["user_id"] == participant["id"]]
    assert len(hits) == 1
    assert hits[0]["triage_count"] >= 1
    assert hits[0]["last_activity"] is not None

    # Open the identified record.
    hr = client.get(
        f"/clinical/participants/{participant['id']}/history",
        headers=clinician["headers"],
    )
    assert hr.status_code == 200, hr.text
    body = hr.json()
    assert body["participant"]["email"] == participant["email"]
    assert len(body["triage"]) >= 1
    assert body["triage"][0]["overall_state"] in {"GREEN", "YELLOW", "RED"}

    # Both accesses were audited.
    assert asyncio.run(_count_view_audits(clinician["id"])) >= 2


def test_history_surfaces_enrollment(client: Any) -> None:
    participant = register(client, "PATIENT")
    _enroll(client, participant["headers"])
    clinician = _make_clinician(client)

    hr = client.get(
        f"/clinical/participants/{participant['id']}/history",
        headers=clinician["headers"],
    )
    assert hr.status_code == 200, hr.text
    enrollment = hr.json()["enrollment"]
    assert enrollment["enrolled"] is True
    assert enrollment["age_range"] == "40-49"
    assert enrollment["biological_sex"] == "MALE"
    assert enrollment["region"] == "NG"
    assert enrollment["jurisdiction"] == "NDPA"
    # Salted hash only — never the raw MRN.
    assert enrollment["patient_id_hash"] is not None
    assert len(enrollment["patient_id_hash"]) == 64
    assert enrollment["consents"] == ["TOI_IMAGING", "TRIAGE"]


def test_history_without_enrollment_reports_not_enrolled(client: Any) -> None:
    participant = _seed_participant(client)
    clinician = _make_clinician(client)

    hr = client.get(
        f"/clinical/participants/{participant['id']}/history",
        headers=clinician["headers"],
    )
    assert hr.status_code == 200, hr.text
    assert hr.json()["enrollment"]["enrolled"] is False


def test_history_unknown_participant_is_404(client: Any) -> None:
    clinician = _make_clinician(client)
    rid = uuid.uuid4()
    r = client.get(
        f"/clinical/participants/{rid}/history", headers=clinician["headers"]
    )
    assert r.status_code == 404, r.text
