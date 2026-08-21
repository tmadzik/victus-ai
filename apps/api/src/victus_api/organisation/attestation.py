"""The non-underwriting attestation guarding individual-member views.

"Which of our members are at high risk" is care coordination when it routes
someone into a wellness programme, and risk selection when it prices or declines
them. The query is identical; only the intent differs, and software cannot read
intent.

So the platform does the two things it can. It makes the operator state the
purpose on the record before the view opens, and it logs every access made under
that statement. Neither prevents misuse by someone determined to misuse it. What
they do is remove the defence of ambiguity: a funder challenged over risk
selection cannot claim the tool merely showed them something, because a named
person attested to a purpose on a date and every record they opened is listed
beneath it.

This is also why the attestation expires. One signed at onboarding and honoured
forever is a checkbox. One that lapses produces a dated trail, and the trail is
the entire point.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.core.deps import CurrentUser, DbSession
from victus_api.core.exceptions import AuthorizationError
from victus_api.core.logging import get_logger
from victus_api.db.models import CareUseAttestation, User, UserRole

log = get_logger(__name__)

# The wording an operator agrees to. Versioned because it will change, and what
# somebody signed must remain recoverable after it does.
CARE_USE_ATTESTATION_VERSION = "care-use-v1"

CARE_USE_ATTESTATION_TEXT = (
    "I confirm that I am accessing individual member screening results for care "
    "management — to route this person into wellness, care or follow-up — and "
    "not for underwriting, premium rating, risk selection, eligibility or any "
    "other decision affecting this person's cover or its price. I understand "
    "that every record I open under this confirmation is logged against my name."
)

# Ninety days: long enough not to be a nuisance mid-programme, short enough that
# a lapsed care manager loses access rather than retaining it indefinitely.
ATTESTATION_TTL_DAYS = 90


async def current_attestation(
    db: AsyncSession, *, user_id: uuid.UUID, now: datetime | None = None
) -> CareUseAttestation | None:
    """The user's live attestation, or ``None`` if absent, expired or revoked."""
    moment = now or datetime.now(UTC)
    return (
        await db.execute(
            select(CareUseAttestation)
            .where(
                CareUseAttestation.user_id == user_id,
                CareUseAttestation.revoked_at.is_(None),
                CareUseAttestation.expires_at > moment,
            )
            .order_by(CareUseAttestation.attested_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def record_attestation(
    db: AsyncSession,
    *,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
    version: str = CARE_USE_ATTESTATION_VERSION,
    ttl_days: int = ATTESTATION_TTL_DAYS,
) -> CareUseAttestation:
    """Record a fresh attestation for ``user``.

    Only a care manager may attest. Allowing any role to would let an
    organisation admin clear the gate on a care manager's behalf, which turns a
    personal declaration into an administrative formality — the opposite of what
    it is for.
    """
    if user.role is not UserRole.CARE_MANAGER:
        raise AuthorizationError(
            "Only a care manager can give the care-use attestation; it is a "
            "personal declaration about how this operator will use member data.",
            details={"role": user.role.value},
        )

    now = datetime.now(UTC)
    row = CareUseAttestation(
        user_id=user.id,
        version=version,
        attested_at=now,
        expires_at=now + timedelta(days=ttl_days),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(row)
    await db.flush()
    log.info(
        "care_use_attested",
        user_id=str(user.id),
        version=version,
        expires_at=row.expires_at.isoformat(),
    )
    return row


def require_care_attestation() -> Callable[..., Awaitable[User]]:
    """Dependency: a care manager with a live attestation, or 403.

    The error names the reason rather than returning a bare denial, because the
    fix is different in each case — attest, renew, or you are the wrong role —
    and an operator who cannot tell which will simply ask someone to widen their
    permissions.

    ``CurrentUser`` and ``DbSession`` must be imported at module scope, not
    inside this factory. ``from __future__ import annotations`` makes the inner
    function's annotations strings, and FastAPI resolves them against the
    module globals — a local import leaves them unresolvable, at which point
    FastAPI silently treats both as query parameters and every call 422s.
    """
    async def _checker(user: CurrentUser, db: DbSession) -> User:
        if user.role is not UserRole.CARE_MANAGER:
            raise AuthorizationError(
                "Individual member results are restricted to care managers.",
                details={"required_roles": [UserRole.CARE_MANAGER.value]},
            )
        attestation = await current_attestation(db, user_id=user.id)
        if attestation is None:
            raise AuthorizationError(
                "A current care-use attestation is required before individual "
                "member results can be opened.",
                details={
                    "attestation_version": CARE_USE_ATTESTATION_VERSION,
                    "attestation_text": CARE_USE_ATTESTATION_TEXT,
                },
            )
        return user

    return _checker
