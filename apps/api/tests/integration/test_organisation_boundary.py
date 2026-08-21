"""The organisation boundary — the isolation guarantee the funder pathway sells.

Tenancy is a deployment boundary: one instance, one database, one organisation.
That removes the usual multi-tenant failure (a forgotten ``WHERE
organisation_id = ...`` disclosing one funder's members to another) but leaves a
narrower one — a deployment writing records for an organisation it does not
serve, through a misconfiguration, a restored backup pointed at the wrong
database, or a seed carrying an id from elsewhere.

These tests pin that the boundary fails closed in every direction, because a
boundary that degrades to a warning is not a boundary.

Real Postgres: the check constraint and the FK are part of what is being
asserted, and neither exists in a stubbed session. Every test runs inside a
transaction that is rolled back, so organisations never leak between them — the
unique org_code and the single-organisation assertion would collide if they did.
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
from victus_api.db.models import Organisation, ServiceModel, UserRole
from victus_api.organisation.service import (
    OrganisationBoundaryError,
    assert_single_organisation,
    assert_within_boundary,
    resolve_deployment_organisation,
)


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    """A session whose work is always rolled back."""
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


async def _add_org(
    db: AsyncSession, code: str, name: str = "Acme Health"
) -> Organisation:
    row = Organisation(
        org_code=code, display_name=name, service_model=ServiceModel.PLATFORM
    )
    db.add(row)
    await db.flush()
    return row


# --- resolving the deployment's organisation ---------------------------------


async def test_unbound_deployment_resolves_to_no_organisation(client: Any) -> None:
    async with _session() as db:
        # Victus' own research and pilot instances serve no organisation. That is a
        # real state, not missing configuration.
        assert await resolve_deployment_organisation(db, settings=_settings(None)) is None


async def test_bound_deployment_resolves_its_organisation(client: Any) -> None:
    async with _session() as db:
        await _add_org(db, "ACME")
        org = await resolve_deployment_organisation(db, settings=_settings("ACME"))
        assert org is not None
        assert org.org_code == "ACME"


async def test_refuses_to_resolve_an_organisation_that_does_not_exist(client: Any) -> None:
    async with _session() as db:
        # The signature of a deployment pointed at the wrong database. Booting here
        # would accept screening data without knowing whose it is.
        with pytest.raises(OrganisationBoundaryError, match="no organisation with that"):
            await resolve_deployment_organisation(db, settings=_settings("GHOST"))


# --- the write boundary ------------------------------------------------------


async def test_write_for_the_served_organisation_is_allowed(client: Any) -> None:
    async with _session() as db:
        org = await _add_org(db, "ACME")
        await assert_within_boundary(
            db, settings=_settings("ACME"), organisation_id=org.id
        )


async def test_write_for_a_different_organisation_is_refused(client: Any) -> None:
    async with _session() as db:
        # The disclosure this whole design exists to prevent.
        await _add_org(db, "ACME")
        with pytest.raises(OrganisationBoundaryError, match="Refusing the write"):
            await assert_within_boundary(
                db, settings=_settings("ACME"), organisation_id=uuid.uuid4()
            )


async def test_unstamped_write_on_a_bound_deployment_is_refused(client: Any) -> None:
    async with _session() as db:
        # An unstamped record is invisible to the organisation's own dashboard and
        # escapes their retention and erasure scope — silently. Failing closed here
        # is the difference between a bug and an undiscoverable one.
        await _add_org(db, "ACME")
        with pytest.raises(OrganisationBoundaryError, match="no organisation"):
            await assert_within_boundary(
                db, settings=_settings("ACME"), organisation_id=None
            )


async def test_organisation_data_is_refused_on_an_unbound_deployment(client: Any) -> None:
    async with _session() as db:
        # The reverse leak: organisation data landing on a shared or research
        # instance, which is not that organisation's and not covered by their
        # agreement.
        with pytest.raises(OrganisationBoundaryError, match="serves no organisation"):
            await assert_within_boundary(
                db, settings=_settings(None), organisation_id=uuid.uuid4()
            )


async def test_unbound_deployment_accepts_unstamped_writes(client: Any) -> None:
    async with _session() as db:
        await assert_within_boundary(
            db, settings=_settings(None), organisation_id=None
        )


# --- the merged-database check -----------------------------------------------


async def test_single_organisation_holds_for_zero_and_one(client: Any) -> None:
    async with _session() as db:
        await assert_single_organisation(db)
        await _add_org(db, "ACME")
        await assert_single_organisation(db)


async def test_two_organisations_in_one_database_is_refused(client: Any) -> None:
    async with _session() as db:
        # Not a data-model error — evidence that two funders' member data has been
        # merged. Caught at startup, because by the time a query returns both
        # organisations' members the disclosure has already happened.
        await _add_org(db, "ACME")
        await _add_org(db, "GLOBEX", name="Globex Assurance")
        with pytest.raises(OrganisationBoundaryError, match="holds 2 organisations"):
            await assert_single_organisation(db)


# --- consent and roles -------------------------------------------------------


async def test_training_export_consent_defaults_to_false(client: Any) -> None:
    async with _session() as db:
        # An unanswered question must never read as consent to export member data.
        org = await _add_org(db, "ACME")
        await db.refresh(org)
        assert org.training_export_consent is False
        assert org.training_export_consent_version is None


async def test_consent_without_a_named_agreement_is_rejected(client: Any) -> None:
    async with _session() as db:
        # A bare TRUE cannot be audited later, and "which terms did they agree to"
        # is exactly the question asked when the terms change.
        org = await _add_org(db, "ACME")
        org.training_export_consent = True
        with pytest.raises(Exception) as excinfo:
            await db.flush()
        assert "export_consent_needs_version" in str(excinfo.value)


def test_organisation_roles_exist_and_are_distinct_from_victus_roles() -> None:
    assert UserRole.ORG_ADMIN in UserRole
    assert UserRole.CARE_MANAGER in UserRole
    # CARE_MANAGER is deliberately not CLINICIAN: it is the organisation's
    # staff, and the individual-level view it will unlock is the one that must
    # never become an underwriting tool.
    assert UserRole.CARE_MANAGER is not UserRole.CLINICIAN


def test_every_service_model_the_pathway_offers_is_representable() -> None:
    # Use Victus' platform, be seen at Victus' facilities, or have Victus attend
    # the organisation's site.
    assert {m.value for m in ServiceModel} == {"PLATFORM", "FACILITIES", "IN_HOUSE"}
