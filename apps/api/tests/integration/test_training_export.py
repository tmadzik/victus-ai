"""The consent gate in front of the training export.

De-identification decides *what* may leave. This decides *whether* anything may
leave at all, and it is the half a funder's legal team will actually read: their
members' data does not go anywhere until they have agreed, in a named version of
an agreement, that it can.

Real Postgres, each test inside a rolled-back transaction so organisations do
not leak between them.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from victus_api.config import Settings
from victus_api.db.models import Organisation, ServiceModel
from victus_api.export.service import (
    CALIBRATION_RELEASE,
    ExportNotPermittedError,
    assert_export_permitted,
    build_training_export,
    record_export_consent,
)


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as db:
            await db.begin()
            try:
                yield db
            finally:
                await db.rollback()
    finally:
        await engine.dispose()


def _settings(org_code: str | None) -> Settings:
    return Settings(**{"organisation_code": org_code})  # type: ignore[arg-type]


async def _org(db: AsyncSession, code: str = "ACME", **kw: Any) -> Organisation:
    row = Organisation(
        org_code=code,
        display_name="Acme Health",
        service_model=ServiceModel.PLATFORM,
        **kw,
    )
    db.add(row)
    await db.flush()
    return row


# --- the gate ----------------------------------------------------------------


async def test_export_is_refused_without_consent(client: Any) -> None:
    async with _session() as db:
        await _org(db)
        with pytest.raises(ExportNotPermittedError, match="has not consented"):
            await assert_export_permitted(db, settings=_settings("ACME"))


async def test_refusal_is_an_error_not_an_empty_export(client: Any) -> None:
    # Returning zero rows would be indistinguishable from a deployment that
    # simply has no data. "They said no" and "there was nothing" must not look
    # the same to whoever reads the output.
    async with _session() as db:
        await _org(db)
        with pytest.raises(ExportNotPermittedError):
            await build_training_export(db, settings=_settings("ACME"))


async def test_export_is_permitted_once_consent_names_an_agreement(
    client: Any,
) -> None:
    async with _session() as db:
        org = await _org(db)
        await record_export_consent(
            db, organisation_id=org.id, version="dpa-2026-v1", granted=True
        )
        permitted = await assert_export_permitted(db, settings=_settings("ACME"))

        assert permitted is not None
        assert permitted.training_export_consent_version == "dpa-2026-v1"
        assert permitted.training_export_consent_at is not None


async def test_withdrawal_clears_the_agreement_version(client: Any) -> None:
    # A stale version beside a FALSE would read as a live agreement that no
    # longer holds.
    async with _session() as db:
        org = await _org(db)
        await record_export_consent(
            db, organisation_id=org.id, version="dpa-2026-v1", granted=True
        )
        await record_export_consent(
            db, organisation_id=org.id, version="dpa-2026-v1", granted=False
        )

        assert org.training_export_consent is False
        assert org.training_export_consent_version is None
        assert org.training_export_consent_at is None

        with pytest.raises(ExportNotPermittedError):
            await assert_export_permitted(db, settings=_settings("ACME"))


async def test_consent_is_not_inherited_by_a_different_organisation(
    client: Any,
) -> None:
    # One funder agreeing must never license another funder's data.
    async with _session() as db:
        consenting = await _org(db, code="ACME")
        await record_export_consent(
            db, organisation_id=consenting.id, version="dpa-2026-v1", granted=True
        )
        await _org(db, code="GLOBEX")

        with pytest.raises(ExportNotPermittedError, match="GLOBEX"):
            await assert_export_permitted(db, settings=_settings("GLOBEX"))


async def test_unknown_organisation_id_is_refused(client: Any) -> None:
    async with _session() as db:
        with pytest.raises(ExportNotPermittedError, match="No organisation"):
            await record_export_consent(
                db, organisation_id=uuid.uuid4(), version="v1", granted=True
            )


async def test_research_deployment_needs_no_organisation_consent(
    client: Any,
) -> None:
    # Victus' own instances export their own data; there is no funder to ask.
    async with _session() as db:
        assert await assert_export_permitted(db, settings=_settings(None)) is None


# --- what the payload carries -------------------------------------------------


async def test_payload_carries_no_organisation_identifier(client: Any) -> None:
    # The substance of "not linked to the organisation": once pooled, rows
    # cannot be attributed back to a funder from their contents.
    async with _session() as db:
        org = await _org(db)
        await record_export_consent(
            db, organisation_id=org.id, version="dpa-2026-v1", granted=True
        )
        export = await build_training_export(db, settings=_settings("ACME"))
        payload = export.to_dict()

        assert "organisation_code" not in payload
        assert "organisation_id" not in payload
        assert "ACME" not in str(payload)
        # The suppression report always rides along, even when empty, so a
        # recipient can tell a thin cohort from a heavily-suppressed one.
        assert "suppression" in payload
        assert payload["consent_version"] == "dpa-2026-v1"


def test_the_release_allowlist_excludes_every_identifier() -> None:
    # Guards the real spec, not a test fixture: the fields actually shipped.
    forbidden = {"user_id", "id", "external_subject_id", "notes", "organisation_id"}
    assert not (CALIBRATION_RELEASE.release & forbidden)
    # Skin tone leaves only as a coarsened band, never as the raw grade.
    assert "skin_tone_band" in CALIBRATION_RELEASE.release
    assert "fitzpatrick_scale" not in CALIBRATION_RELEASE.release
    assert "skin_tone_estimate" not in CALIBRATION_RELEASE.release
