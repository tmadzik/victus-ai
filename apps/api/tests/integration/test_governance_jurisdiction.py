"""Integration: self-service erasure records the jurisdiction of the
participant's enrolment site (e.g. NG → NDPA), not the request body's value.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import register
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


def _erase(client: Any, site_code: str) -> dict[str, Any]:
    user = register(client, "PATIENT")
    asyncio.run(_set_site(user["email"], site_code))
    r = client.post(
        "/governance/erase-account",
        headers=user["headers"],
        json={"confirm_email": user["email"], "jurisdiction": "GDPR"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_nigeria_site_records_ndpa(client: Any) -> None:
    # Despite the request asking for GDPR, an NG participant is governed by NDPA.
    assert _erase(client, "NG")["jurisdiction"] == "NDPA"


def test_zimbabwe_site_records_popia(client: Any) -> None:
    assert _erase(client, "ZW")["jurisdiction"] == "POPIA"


def test_unmapped_site_keeps_requested_jurisdiction(client: Any) -> None:
    # An unmapped site falls back to the request's value (GDPR here).
    assert _erase(client, "DEFAULT")["jurisdiction"] == "GDPR"
