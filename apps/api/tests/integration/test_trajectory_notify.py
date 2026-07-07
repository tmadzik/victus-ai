"""Integration: the trajectory-rise nudge fans out to a participant's site
clinicians (and only them)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import register, unread_count
from victus_api.db.models import NotificationType, User
from victus_api.notifications.service import notify_site_clinicians

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


async def _fan_out(site_code: str) -> int:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            n = await notify_site_clinicians(
                s,
                type_=NotificationType.RISK_TRAJECTORY_RISE,
                title="Rising NCD risk",
                body="A participant at your site has a rising risk trajectory.",
                site_code=site_code,
                resource="/clinical/x",
            )
            await s.commit()
            return n
    finally:
        await engine.dispose()


def test_nudge_scopes_to_site_clinicians(client: Any) -> None:
    same_site = register(client, "CLINICIAN")  # stamped with the test site
    other_site = register(client, "CLINICIAN")
    patient = register(client, "PATIENT")  # excluded by role
    asyncio.run(_set_site(other_site["email"], "OTHER_SITE"))

    site = "DEFAULT"  # the test instance's SITE_CODE
    before = unread_count(client, same_site["headers"])
    created = asyncio.run(_fan_out(site))

    assert created >= 1
    # A clinician at the site is notified.
    assert unread_count(client, same_site["headers"]) > before
    # A clinician at a different site is not.
    assert unread_count(client, other_site["headers"]) == 0
    # A participant never receives the clinician nudge (role filter).
    assert unread_count(client, patient["headers"]) == 0
