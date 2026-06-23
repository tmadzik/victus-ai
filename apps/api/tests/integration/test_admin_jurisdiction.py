"""Integration: admin-initiated subject anonymisation records the jurisdiction
of the *subject's* enrolment site (e.g. NG → NDPA), not the request body's value.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import grant_consent, register
from victus_api.db.models import User, UserRole

pytestmark = pytest.mark.integration


async def _promote(email: str, role: UserRole) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            await s.execute(
                update(User).where(User.email == email).values(role=role)
            )
            await s.commit()
    finally:
        await engine.dispose()


async def _set_user_site(email: str, site_code: str) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            await s.execute(
                update(User).where(User.email == email).values(site_code=site_code)
            )
            await s.commit()
    finally:
        await engine.dispose()


def _admin(client: Any) -> dict[str, Any]:
    a = register(client, "PATIENT")
    asyncio.run(_promote(a["email"], UserRole.ADMIN))
    return a


def test_admin_subject_anonymisation_uses_subject_site(client: Any) -> None:
    # A clinician enrolled at the NG site registers a study subject…
    clinician = register(client, "PATIENT")
    asyncio.run(_promote(clinician["email"], UserRole.CLINICIAN))
    asyncio.run(_set_user_site(clinician["email"], "NG"))
    grant_consent(client, clinician["headers"], "TOI_IMAGING")
    subj = client.post(
        "/study/subjects",
        headers=clinician["headers"],
        json={
            "external_subject_id": f"SUBJ-{uuid.uuid4().hex[:8]}",
            "age_years": 47,
            "sex_assigned_at_birth": "FEMALE",
            "fitzpatrick_scale": "V",
            "consent_protocol_version": "v1.0",
        },
    )
    assert subj.status_code in (200, 201), subj.text
    subject_id = subj.json()["id"]

    # …and an admin proposes anonymisation, asking for GDPR in the body.
    admin = _admin(client)
    propose = client.post(
        f"/governance/admin/subjects/{subject_id}/anonymise",
        headers=admin["headers"],
        json={"jurisdiction": "GDPR", "request_basis": "ADMIN_ACTION"},
    )
    assert propose.status_code in (200, 201, 202), propose.text
    # The recorded jurisdiction is the subject's site regime, not the body value.
    assert propose.json()["jurisdiction"] == "NDPA"
