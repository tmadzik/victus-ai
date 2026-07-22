"""Integration: a rising contactless (TOI) vital-sign trend nudges the
participant's site clinicians — end-to-end through the real assess endpoint,
the same path the Mobile Clinic Gateway kiosk worker drives."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import (
    assess_toi,
    grant_consent,
    register,
    unread_count,
)
from victus_api.db.models import User

pytestmark = pytest.mark.integration


async def _set_site(email: str, site_code: str) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            await s.execute(
                update(User).where(User.email == email).values(site_code=site_code)
            )
            await s.commit()
    finally:
        await engine.dispose()


def test_toi_rise_nudges_site_clinicians(client: Any) -> None:
    participant = register(client, "PATIENT")  # stamped with the test site
    grant_consent(client, participant["headers"], "TOI_IMAGING")

    same_site = register(client, "CLINICIAN")
    other_site = register(client, "CLINICIAN")
    asyncio.run(_set_site(other_site["email"], "OTHER_SITE"))

    # First contactless check — no prior, so nothing can trend yet.
    assess_toi(client, participant["headers"], hr_bpm=60.0)
    assert unread_count(client, same_site["headers"]) == 0

    before = unread_count(client, same_site["headers"])
    # A markedly higher resting heart rate tips the trajectory into a
    # significant upward crossing.
    assess_toi(client, participant["headers"], hr_bpm=98.0)

    # A clinician at the participant's site is nudged.
    assert unread_count(client, same_site["headers"]) > before
    # A clinician at a different site is not.
    assert unread_count(client, other_site["headers"]) == 0
    # The participant never receives the clinician nudge.
    assert unread_count(client, participant["headers"]) == 0

    # And the inbox must actually RENDER. Counting unread hits COUNT(*) and never
    # deserialises a row, so it cannot catch a notification type that is missing
    # from the response enum — which 500s the whole list endpoint.
    listed = client.get("/notifications/me?limit=20", headers=same_site["headers"])
    assert listed.status_code == 200, listed.text
    types = [n["type"] for n in listed.json()["notifications"]]
    assert "RISK_TRAJECTORY_RISE" in types
