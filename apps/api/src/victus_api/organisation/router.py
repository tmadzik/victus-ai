"""Organisation dashboard HTTP layer.

Two tiers, deliberately separated at the routing level rather than by a
parameter on one endpoint:

* ``/organisation/cohort`` — suppressed aggregates. Open to the organisation's
  own admins and care managers. Names nobody.
* ``/organisation/members/flagged`` — named members for care routing. Care
  managers only, behind a live non-underwriting attestation, and every call
  written to the audit log.

Splitting them means the individual-level path cannot be reached by passing a
different argument to the aggregate one. A single endpoint with a
``detail=true`` flag would put the whole control on a default, and defaults are
exactly what gets changed by someone who does not know why it was set.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from victus_api.audit.service import write_audit
from victus_api.core.deps import CurrentUser, DbSession, require_role
from victus_api.db.models import AuditAction, TriageState, UserRole
from victus_api.organisation.attestation import (
    CARE_USE_ATTESTATION_TEXT,
    CARE_USE_ATTESTATION_VERSION,
    current_attestation,
    record_attestation,
    require_care_attestation,
)
from victus_api.organisation.cohort import build_cohort_report, list_flagged_members
from victus_api.organisation.schemas import (
    AttestationResponse,
    AttestationStatusResponse,
    CohortResponse,
    FlaggedMemberListResponse,
)

router = APIRouter(prefix="/organisation", tags=["organisation"])

OrgUser = Annotated[
    CurrentUser,
    Depends(require_role(UserRole.ORG_ADMIN, UserRole.CARE_MANAGER, UserRole.ADMIN)),
]
AttestedCareManager = Annotated[CurrentUser, Depends(require_care_attestation())]


def _client(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


@router.get("/cohort", response_model=CohortResponse)
async def cohort(user: OrgUser, db: DbSession, request: Request) -> CohortResponse:
    """Population view. Every breakdown cell below k is suppressed."""
    report = await build_cohort_report(db)
    ip, ua = _client(request)
    await write_audit(
        db,
        action=AuditAction.ORG_COHORT_VIEWED,
        actor_id=user.id,
        resource="organisation:cohort",
        ip_address=ip,
        user_agent=ua,
        metadata={"members_screened": report.members_screened},
    )
    return CohortResponse(**report.to_dict())


@router.get("/attestation", response_model=AttestationStatusResponse)
async def attestation_status(
    user: OrgUser, db: DbSession
) -> AttestationStatusResponse:
    """Whether this operator may open individual results, and the wording."""
    live = await current_attestation(db, user_id=user.id)
    return AttestationStatusResponse(
        active=live is not None,
        version=CARE_USE_ATTESTATION_VERSION,
        text=CARE_USE_ATTESTATION_TEXT,
        expires_at=live.expires_at if live else None,
    )


@router.post(
    "/attestation",
    response_model=AttestationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attest(
    user: OrgUser, db: DbSession, request: Request
) -> AttestationResponse:
    """Record the care-use declaration for the calling care manager."""
    ip, ua = _client(request)
    row = await record_attestation(db, user=user, ip_address=ip, user_agent=ua)
    await write_audit(
        db,
        action=AuditAction.CARE_USE_ATTESTED,
        actor_id=user.id,
        resource=f"attestation:{row.id}",
        ip_address=ip,
        user_agent=ua,
        metadata={
            "version": row.version,
            "expires_at": row.expires_at.isoformat(),
        },
    )
    return AttestationResponse(
        version=row.version, attested_at=row.attested_at, expires_at=row.expires_at
    )


@router.get("/members/flagged", response_model=FlaggedMemberListResponse)
async def flagged_members(
    user: AttestedCareManager,
    db: DbSession,
    request: Request,
    state: Annotated[
        list[TriageState] | None,
        Query(description="Triage states to include. Defaults to RED and YELLOW."),
    ] = None,
) -> FlaggedMemberListResponse:
    """Members needing care routing, by name.

    The audit entry records the count and the states requested rather than the
    member ids. Copying every id into the audit log would duplicate the very
    data the log exists to police, and grow a second store of member
    identifiers that no erasure path reaches.
    """
    states = tuple(state) if state else (TriageState.RED, TriageState.YELLOW)
    members = await list_flagged_members(db, states=states)

    ip, ua = _client(request)
    await write_audit(
        db,
        action=AuditAction.ORG_MEMBER_RISK_VIEWED,
        actor_id=user.id,
        resource="organisation:members:flagged",
        ip_address=ip,
        user_agent=ua,
        metadata={
            "states": [s.value for s in states],
            "members_returned": len(members),
            "attestation_version": CARE_USE_ATTESTATION_VERSION,
        },
    )

    return FlaggedMemberListResponse(
        members=[m.__dict__ for m in members],  # type: ignore[arg-type]
        count=len(members),
        attestation_version=CARE_USE_ATTESTATION_VERSION,
    )
