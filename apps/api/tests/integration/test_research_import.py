"""Integration: the REDCap/ODK CSV import endpoint for the research corpus."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from tests.integration._helpers import register
from victus_api.db.models import User, UserRole

pytestmark = pytest.mark.integration

CSV = (
    "age,sex,height_cm,weight_kg,waist_cm,systolic_bp,diastolic_bp,hba1c,country\n"
    "54,M,172,99,112,158,98,7.2,NG\n"  # valid → diabetes + HTN + obesity labels
    "40,F,160,70,85,120,80,5.2,NG\n"  # valid → all low/normal
    "bad,F,160,70,85,,,,NG\n"  # invalid age → reported, not aborting
)


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


def _researcher(client: Any) -> dict[str, Any]:
    r = register(client, "PATIENT")
    asyncio.run(_promote(r["email"], UserRole.CHW))
    return r


def test_csv_import_reports_per_row_outcomes(client: Any) -> None:
    researcher = _researcher(client)
    resp = client.post(
        "/research/triage-cases/import",
        headers={**researcher["headers"], "Content-Type": "text/csv"},
        content=CSV,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 2
    assert body["failed"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 2  # zero-based index of the bad row


def test_import_requires_researcher_role(client: Any) -> None:
    patient = register(client, "PATIENT")
    resp = client.post(
        "/research/triage-cases/import",
        headers={**patient["headers"], "Content-Type": "text/csv"},
        content=CSV,
    )
    assert resp.status_code == 403
