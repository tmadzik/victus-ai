"""Integration: front-of-platform enrollment (profile + consent + gate + erasure).

Runs against the live app + real Postgres. Proves the enrollment gate is
satisfied only after both pathway consents are recorded, that the external
patient id is stored solely as a salted hash, and that account erasure scrubs
the identified fields while keeping the de-identified strata.
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

from victus_api.db.models import ParticipantProfile

from ._helpers import register

pytestmark = pytest.mark.integration


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "patient_id": "MRN-12345",
        "age_range": "30-39",
        "biological_sex": "FEMALE",
        "region": "NG",
        "race_ethnicity": "Yoruba",
        "consent_triage": True,
        "consent_toi_imaging": True,
        "consent_research": True,
    }
    base.update(overrides)
    return base


async def _profile(user_id: str) -> ParticipantProfile | None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as db:
            row = (
                await db.execute(
                    select(ParticipantProfile).where(
                        ParticipantProfile.user_id == uuid.UUID(user_id)
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                db.expunge(row)
            return row
    finally:
        await engine.dispose()


def test_enroll_flow_and_gate(client: Any) -> None:
    patient = register(client, "PATIENT")
    h = patient["headers"]

    before = client.get("/enrollment/status", headers=h).json()
    assert before["enrolled"] is False and before["has_profile"] is False
    assert set(before["missing_consents"]) == {"TRIAGE", "TOI_IMAGING"}

    resp = client.post("/enrollment", headers=h, json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Patient id is stored only as a salted hash — never the raw MRN.
    assert body["patient_id_hash"] and body["patient_id_hash"] != "MRN-12345"
    assert len(body["patient_id_hash"]) == 64
    assert body["jurisdiction"] == "NDPA"  # NG → NDPA

    after = client.get("/enrollment/status", headers=h).json()
    assert after["enrolled"] is True and after["missing_consents"] == []


def test_enroll_requires_both_pathway_consents(client: Any) -> None:
    patient = register(client, "PATIENT")
    resp = client.post(
        "/enrollment",
        headers=patient["headers"],
        json=_payload(consent_toi_imaging=False),
    )
    assert resp.status_code == 422, resp.text


def test_enroll_is_idempotent_same_hash(client: Any) -> None:
    patient = register(client, "PATIENT")
    h = patient["headers"]
    first = client.post("/enrollment", headers=h, json=_payload()).json()
    # Re-enrolling with the same patient id updates the row and yields the same
    # hash (no duplicate profile, deterministic hashing).
    second = client.post("/enrollment", headers=h, json=_payload(full_name="Ada L.")).json()
    assert first["id"] == second["id"]
    assert first["patient_id_hash"] == second["patient_id_hash"]
    assert second["full_name"] == "Ada L."


def test_account_erasure_scrubs_profile(client: Any) -> None:
    patient = register(client, "PATIENT")
    h = patient["headers"]
    client.post("/enrollment", headers=h, json=_payload())

    erase = client.post(
        "/governance/erase-account",
        headers=h,
        json={"confirm_email": patient["email"], "request_basis": "ACCOUNT_DELETION"},
    )
    assert erase.status_code == 200, erase.text

    profile = asyncio.run(_profile(patient["id"]))
    assert profile is not None
    # Direct identifiers + special-category + external-id hash are gone…
    assert profile.full_name is None
    assert profile.email is None
    assert profile.race_ethnicity is None
    assert profile.patient_id_hash is None
    assert profile.erased_at is not None
    # …but the de-identified research strata are retained.
    assert profile.age_range == "30-39"
    assert profile.region == "NG"
    assert profile.biological_sex.value == "FEMALE"
