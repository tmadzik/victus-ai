"""Deployment-to-organisation binding, and the boundary that isolation rests on.

Tenancy here is a *deployment* boundary. One instance and one database serve
exactly one organisation, the way the ZW and NG pilots each run their own. The
rejected alternative — a shared instance filtering every query by organisation —
puts the isolation guarantee in every query anyone writes from now on, and one
forgotten ``WHERE organisation_id = ...`` discloses one funder's members to
another. A boundary you cannot forget to apply is worth more than a filter that
is correct on the day it is written.

That leaves exactly one way to breach it: writing a record stamped with an
organisation this deployment does not serve — through a misconfiguration, a
restored backup pointed at the wrong database, or a seed script carrying an id
from somewhere else. :func:`assert_within_boundary` is what makes that loud
rather than silent, and :func:`resolve_deployment_organisation` refuses to boot
a deployment whose configured organisation does not resolve.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.config import Settings
from victus_api.core.logging import get_logger
from victus_api.db.models import Organisation

log = get_logger(__name__)


class OrganisationBoundaryError(RuntimeError):
    """A write would attach a record to an organisation this deployment does
    not serve, or the deployment's organisation cannot be resolved.

    Never caught and converted to a warning. A deployment that cannot say which
    organisation it serves has no business writing that organisation's health
    data, and one that is about to write another organisation's data must stop
    rather than continue with a note in the log.
    """


async def resolve_deployment_organisation(
    db: AsyncSession, *, settings: Settings
) -> Organisation | None:
    """Return the organisation this deployment serves, or ``None`` if it serves
    no organisation (Victus' own research and pilot instances).

    Raises :class:`OrganisationBoundaryError` when ``ORGANISATION_CODE`` is set
    but does not resolve to exactly one row. Failing to boot is the correct
    outcome: the alternative is an instance that accepts screening data without
    knowing whose it is.
    """
    code = (settings.organisation_code or "").strip()
    if not code:
        return None

    row = (
        await db.execute(select(Organisation).where(Organisation.org_code == code))
    ).scalar_one_or_none()

    if row is None:
        raise OrganisationBoundaryError(
            f"ORGANISATION_CODE is '{code}' but no organisation with that "
            "org_code exists in this database. Either the deployment is "
            "pointed at the wrong database, or the organisation was never "
            "provisioned. Refusing to serve data for an organisation this "
            "instance cannot identify."
        )
    return row


async def assert_within_boundary(
    db: AsyncSession,
    *,
    settings: Settings,
    organisation_id: uuid.UUID | None,
) -> None:
    """Refuse a write that would cross the deployment's organisation boundary.

    Called before persisting any org-scoped record. Both mismatches are
    failures, in both directions:

    * an organisation-bound deployment writing a record for a *different*
      organisation, or one with no organisation at all;
    * an unbound deployment (Victus research/pilot) writing a record stamped
      with some organisation — which would mean organisation data had reached
      an instance that is not that organisation's.
    """
    expected = await resolve_deployment_organisation(db, settings=settings)

    if expected is None:
        if organisation_id is not None:
            raise OrganisationBoundaryError(
                "This deployment serves no organisation (ORGANISATION_CODE is "
                f"unset), but a record was stamped with organisation "
                f"{organisation_id}. Organisation data must not land on a "
                "shared or research instance."
            )
        return

    if organisation_id is None:
        raise OrganisationBoundaryError(
            f"This deployment serves organisation '{expected.org_code}', but a "
            "record was written with no organisation. An unstamped record is "
            "invisible to that organisation's own dashboard and would silently "
            "escape their retention and erasure scope."
        )

    if organisation_id != expected.id:
        raise OrganisationBoundaryError(
            f"This deployment serves organisation '{expected.org_code}' "
            f"({expected.id}), but a record was stamped with organisation "
            f"{organisation_id}. Refusing the write."
        )


async def assert_single_organisation(db: AsyncSession) -> None:
    """Assert the database holds at most one organisation.

    A second row is not a data-model error — it is evidence that two funders'
    data has been merged into one database, which is the failure this whole
    design exists to prevent. Checked at startup because by the time a query
    returns two organisations' members, the disclosure has already happened.
    """
    count = (await db.execute(select(func.count()).select_from(Organisation))).scalar_one()
    if count > 1:
        raise OrganisationBoundaryError(
            f"This database holds {count} organisations. A deployment serves "
            "exactly one. Two organisations in one database means their member "
            "data has been merged — stop and investigate before serving traffic."
        )
