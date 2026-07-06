"""Referral orchestration: create + status lifecycle, both audited."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.config import Settings
from victus_api.core.exceptions import NotFoundError
from victus_api.db.models import (
    AuditAction,
    NotificationType,
    Referral,
    ReferralStatus,
    User,
)
from victus_api.notifications.service import notify_user
from victus_api.referrals.schemas import (
    CreateReferralRequest,
    RecordReferralOutcomeRequest,
    ReferralResponse,
    UpdateReferralStatusRequest,
)

_REFERRALS_PATH = "/referrals"


def _to_response(row: Referral) -> ReferralResponse:
    return ReferralResponse(
        id=row.id,
        participant_user_id=row.participant_user_id,
        created_by_user_id=row.created_by_user_id,
        source_triage_assessment_id=row.source_triage_assessment_id,
        destination_type=row.destination_type.value,
        destination_name=row.destination_name,
        reason=row.reason,
        urgency=row.urgency.value,
        status=row.status.value,
        notes=row.notes,
        outcome=row.outcome.value,
        outcome_recorded_at=row.outcome_recorded_at,
        outcome_notes=row.outcome_notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_referral(
    db: AsyncSession,
    *,
    actor: User,
    settings: Settings,
    payload: CreateReferralRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> ReferralResponse:
    participant = await db.get(User, payload.participant_user_id)
    if participant is None:
        raise NotFoundError("Participant not found.")

    row = Referral(
        participant_user_id=payload.participant_user_id,
        created_by_user_id=actor.id,
        source_triage_assessment_id=payload.source_triage_assessment_id,
        destination_type=payload.destination_type,
        destination_name=payload.destination_name,
        reason=payload.reason,
        urgency=payload.urgency,
        status=ReferralStatus.PENDING,
        notes=payload.notes,
    )
    db.add(row)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.REFERRAL_CREATED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"referral:{row.id}",
        metadata={
            "participant_id": str(payload.participant_user_id),
            "urgency": payload.urgency.value,
            "destination_type": payload.destination_type.value,
        },
    )

    # Tell the participant they've been referred (in-app + best-effort webhook).
    urgency_label = payload.urgency.value.capitalize()
    await notify_user(
        db,
        settings=settings,
        recipient_user_id=payload.participant_user_id,
        type_=NotificationType.REFERRAL_RAISED,
        title="You have a new referral",
        body=(
            f"Your care team referred you to {payload.destination_name} "
            f"({urgency_label.lower()}). Reason: {payload.reason}"
        ),
        resource_path=_REFERRALS_PATH,
        payload={
            "referral_id": str(row.id),
            "urgency": payload.urgency.value,
            "destination_name": payload.destination_name,
        },
        webhook_fields={
            "Urgency": urgency_label,
            "Destination": payload.destination_name,
        },
    )
    return _to_response(row)


async def list_my_referrals(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 25
) -> list[ReferralResponse]:
    rows = await _list(db, participant_id=user_id, limit=limit)
    return [_to_response(r) for r in rows]


async def list_referrals_for_participant(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 50
) -> list[ReferralResponse]:
    rows = await _list(db, participant_id=user_id, limit=limit)
    return [_to_response(r) for r in rows]


async def _list(
    db: AsyncSession, *, participant_id: uuid.UUID, limit: int
) -> list[Referral]:
    stmt = (
        select(Referral)
        .where(Referral.participant_user_id == participant_id)
        .order_by(desc(Referral.created_at))
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


async def update_referral_status(
    db: AsyncSession,
    *,
    actor: User,
    referral_id: uuid.UUID,
    payload: UpdateReferralStatusRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> ReferralResponse:
    row = await db.get(Referral, referral_id)
    if row is None:
        raise NotFoundError("Referral not found.")

    previous = row.status
    row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    await db.flush()
    # ``updated_at`` is server-generated via onupdate; reload it (and the row)
    # so the response carries the new timestamp without a lazy load.
    await db.refresh(row)

    await write_audit(
        db,
        action=AuditAction.REFERRAL_STATUS_UPDATED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"referral:{row.id}",
        metadata={
            "participant_id": str(row.participant_user_id),
            "from": previous.value,
            "to": payload.status.value,
        },
    )
    return _to_response(row)


async def record_referral_outcome(
    db: AsyncSession,
    *,
    actor: User,
    referral_id: uuid.UUID,
    payload: RecordReferralOutcomeRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> ReferralResponse:
    """Close the care loop: record the facility-confirmed clinical outcome of an
    onward referral. Audited; the outcome is orthogonal to the administrative
    ``status`` lifecycle."""
    row = await db.get(Referral, referral_id)
    if row is None:
        raise NotFoundError("Referral not found.")

    previous = row.outcome
    row.outcome = payload.outcome
    row.outcome_recorded_at = datetime.now(UTC)
    if payload.notes is not None:
        row.outcome_notes = payload.notes
    await db.flush()
    await db.refresh(row)

    await write_audit(
        db,
        action=AuditAction.REFERRAL_OUTCOME_RECORDED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"referral:{row.id}",
        metadata={
            "participant_id": str(row.participant_user_id),
            "from": previous.value,
            "to": payload.outcome.value,
        },
    )
    return _to_response(row)
