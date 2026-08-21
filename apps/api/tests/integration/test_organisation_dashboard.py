"""The organisation dashboard, and the gate in front of individual members.

Cohort aggregates are open to the organisation's own staff. Naming a member is
not: it needs a care manager who has declared on the record that they are
routing people into care rather than underwriting them, and every such call is
written to the audit log.

These tests exercise the HTTP surface, because that is where the gate has to
hold — a control that only works when called through the service layer is not a
control.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from victus_api.db.models import AuditLog, CareUseAttestation, User, UserRole

from ._helpers import _set_role, register


@asynccontextmanager
async def _db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with AsyncSession(engine) as db:
            yield db
            await db.commit()
    finally:
        await engine.dispose()


async def _expire_attestations(email: str) -> None:
    async with _db() as db:
        user = (
            await db.execute(select(User).where(User.email == email.lower()))
        ).scalar_one()
        await db.execute(
            update(CareUseAttestation)
            .where(CareUseAttestation.user_id == user.id)
            .values(expires_at=datetime.now(UTC) - timedelta(days=1))
        )


async def _audit_actions(email: str) -> list[str]:
    async with _db() as db:
        user = (
            await db.execute(select(User).where(User.email == email.lower()))
        ).scalar_one()
        rows = (
            await db.execute(
                select(AuditLog.action).where(AuditLog.actor_id == user.id)
            )
        ).scalars().all()
        return [a.value for a in rows]


# --- cohort tier --------------------------------------------------------------


def test_cohort_is_open_to_organisation_staff(client: Any) -> None:
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.ORG_ADMIN)

    resp = client.get("/organisation/cohort", headers=account["headers"])
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert "members_screened" in body
    assert "triage_distribution" in body
    # The suppression report always rides along so a thin cohort is not
    # mistaken for a biased one.
    assert "suppression" in body


def test_cohort_is_closed_to_a_plain_patient(client: Any) -> None:
    account = register(client, "PATIENT")
    resp = client.get("/organisation/cohort", headers=account["headers"])
    assert resp.status_code == 403


# --- the gate -----------------------------------------------------------------


def test_named_members_are_refused_without_an_attestation(client: Any) -> None:
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.CARE_MANAGER)

    resp = client.get("/organisation/members/flagged", headers=account["headers"])
    assert resp.status_code == 403
    # The refusal must say what to do about it, or the operator just asks for
    # broader permissions instead of attesting.
    assert "attestation" in resp.text.lower()


def test_an_org_admin_cannot_reach_named_members_even_by_attesting(
    client: Any,
) -> None:
    # An ORG_ADMIN attesting on a care manager's behalf would turn a personal
    # declaration into an administrative formality.
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.ORG_ADMIN)

    attest = client.post("/organisation/attestation", headers=account["headers"])
    assert attest.status_code == 403

    resp = client.get("/organisation/members/flagged", headers=account["headers"])
    assert resp.status_code == 403


def test_attesting_opens_the_individual_view(client: Any) -> None:
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.CARE_MANAGER)

    attest = client.post("/organisation/attestation", headers=account["headers"])
    assert attest.status_code == 201, attest.text
    assert attest.json()["version"] == "care-use-v1"

    resp = client.get("/organisation/members/flagged", headers=account["headers"])
    assert resp.status_code == 200, resp.text
    assert "members" in resp.json()


def test_an_expired_attestation_closes_the_view_again(client: Any) -> None:
    # The reason it expires at all: a lapsed care manager loses access rather
    # than keeping it forever on the strength of one click at onboarding.
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.CARE_MANAGER)
    client.post("/organisation/attestation", headers=account["headers"])
    anyio.run(_expire_attestations, account["email"])

    resp = client.get("/organisation/members/flagged", headers=account["headers"])
    assert resp.status_code == 403


def test_attestation_status_reports_the_wording_and_state(client: Any) -> None:
    # The client never holds its own copy of the text; a stale copy would mean
    # people agreeing to something other than what is recorded against them.
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.CARE_MANAGER)

    before = client.get("/organisation/attestation", headers=account["headers"])
    assert before.status_code == 200
    assert before.json()["active"] is False
    assert "underwriting" in before.json()["text"].lower()

    client.post("/organisation/attestation", headers=account["headers"])
    after = client.get("/organisation/attestation", headers=account["headers"])
    assert after.json()["active"] is True
    assert after.json()["expires_at"] is not None


# --- audit --------------------------------------------------------------------


def test_every_individual_access_is_audited(client: Any) -> None:
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.CARE_MANAGER)
    client.post("/organisation/attestation", headers=account["headers"])
    client.get("/organisation/members/flagged", headers=account["headers"])

    actions = anyio.run(_audit_actions, account["email"])
    assert "CARE_USE_ATTESTED" in actions
    assert "ORG_MEMBER_RISK_VIEWED" in actions


def test_the_audit_entry_does_not_copy_member_ids(client: Any) -> None:
    # Copying every id into the audit log would duplicate the data the log
    # exists to police, into a second store no erasure path reaches.
    import anyio

    account = register(client, "PATIENT")
    anyio.run(_set_role, account["email"], UserRole.CARE_MANAGER)
    client.post("/organisation/attestation", headers=account["headers"])
    client.get("/organisation/members/flagged", headers=account["headers"])

    async def _meta() -> list[dict]:
        async with _db() as db:
            user = (
                await db.execute(
                    select(User).where(User.email == account["email"].lower())
                )
            ).scalar_one()
            rows = (
                await db.execute(
                    select(AuditLog).where(AuditLog.actor_id == user.id)
                )
            ).scalars().all()
            return [r.metadata_json or {} for r in rows]

    for meta in anyio.run(_meta):
        assert "member_ids" not in meta
        assert "user_ids" not in meta
