"""Integration: the clinician participant-record PDF endpoint.

Verifies a clinician can download a real application/pdf for a participant (with
a seeded assessment), that the export is audited as ``mode=export``, and that a
non-clinician is refused.
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


async def _count_export_audits(actor_id: str) -> int:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            n = await s.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.actor_id == uuid.UUID(actor_id),
                    AuditLog.action == AuditAction.CLINICIAN_PARTICIPANT_VIEWED,
                    AuditLog.metadata_json["mode"].astext == "export",
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


def test_clinician_downloads_participant_pdf(client: Any) -> None:
    clinician = _make_clinician(client)
    participant = _seed_participant(client)

    before = asyncio.run(_count_export_audits(clinician["id"]))
    resp = client.get(
        f"/clinical/participants/{participant['id']}/report.pdf",
        headers=clinician["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
    assert "attachment" in resp.headers.get("content-disposition", "")

    after = asyncio.run(_count_export_audits(clinician["id"]))
    assert after == before + 1, "the PDF export must be audited as mode=export"


def test_patient_cannot_download_pdf(client: Any) -> None:
    patient = register(client, "PATIENT")
    other = register(client, "PATIENT")
    resp = client.get(
        f"/clinical/participants/{other['id']}/report.pdf",
        headers=patient["headers"],
    )
    assert resp.status_code == 403
