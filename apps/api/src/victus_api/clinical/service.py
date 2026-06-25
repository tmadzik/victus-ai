"""Clinician participant-review: search + identified history, fully audited.

Read-only. Reuses the per-pathway ``list_assessments_for_user`` services (which
already accept an arbitrary ``user_id``), so there is no new persistence — only
the access itself, which is logged via ``CLINICIAN_PARTICIPANT_VIEWED``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.clinical.report import build_participant_report_pdf
from victus_api.clinical.schemas import ParticipantHistory, ParticipantSummary
from victus_api.core.exceptions import NotFoundError
from victus_api.db.models import AuditAction, ToiAssessment, TriageAssessment, User
from victus_api.toi.service import list_assessments_for_user as list_toi
from victus_api.triage.service import list_assessments_for_user as list_triage

_MAX_HISTORY = 100


async def _counts(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    triage_n = await db.scalar(
        select(func.count())
        .select_from(TriageAssessment)
        .where(TriageAssessment.user_id == user_id)
    )
    toi_n = await db.scalar(
        select(func.count())
        .select_from(ToiAssessment)
        .where(ToiAssessment.user_id == user_id)
    )
    return int(triage_n or 0), int(toi_n or 0)


async def _summary(db: AsyncSession, user: User) -> ParticipantSummary:
    triage_n, toi_n = await _counts(db, user.id)
    last_triage = await db.scalar(
        select(func.max(TriageAssessment.created_at)).where(
            TriageAssessment.user_id == user.id
        )
    )
    last_toi = await db.scalar(
        select(func.max(ToiAssessment.created_at)).where(
            ToiAssessment.user_id == user.id
        )
    )
    last_activity = max([t for t in (last_triage, last_toi) if t is not None], default=None)
    return ParticipantSummary(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        site_code=user.site_code,
        triage_count=triage_n,
        toi_count=toi_n,
        last_activity=last_activity,
    )


async def search_participants(
    db: AsyncSession,
    *,
    actor: User,
    query: str,
    limit: int,
    ip_address: str | None,
    user_agent: str | None,
) -> list[ParticipantSummary]:
    """Find participants by email or name substring. The search itself is audited.

    Erased accounts (email/name tombstoned to NULL) simply will not match a text
    query — their identified record is already gone, by design.
    """
    needle = f"%{query.strip()}%"
    stmt = (
        select(User)
        .where(
            or_(
                User.email.ilike(needle),
                User.full_name.ilike(needle),
            )
        )
        .order_by(User.full_name.asc())
        .limit(limit)
    )
    users = list((await db.scalars(stmt)).all())
    summaries = [await _summary(db, u) for u in users]

    await write_audit(
        db,
        action=AuditAction.CLINICIAN_PARTICIPANT_VIEWED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource="clinical:participants:search",
        metadata={"mode": "search", "query": query, "result_count": len(summaries)},
    )
    return summaries


async def _build_history(
    db: AsyncSession, user_id: uuid.UUID, limit: int
) -> tuple[User, ParticipantHistory]:
    """Fetch a participant's identified record (no audit — callers audit)."""
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("Participant not found.")
    capped = min(limit, _MAX_HISTORY)
    triage = await list_triage(db, user_id=user_id, limit=capped)
    toi = await list_toi(db, user_id=user_id, limit=capped)
    summary = await _summary(db, user)
    return user, ParticipantHistory(participant=summary, triage=triage, toi=toi)


async def get_participant_history(
    db: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    limit: int,
    ip_address: str | None,
    user_agent: str | None,
) -> ParticipantHistory:
    """Return a participant's identified assessment record. The access is audited."""
    _user, history = await _build_history(db, user_id, limit)

    await write_audit(
        db,
        action=AuditAction.CLINICIAN_PARTICIPANT_VIEWED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"clinical:participant:{user_id}",
        metadata={
            "mode": "view",
            "participant_id": str(user_id),
            "triage_count": history.participant.triage_count,
            "toi_count": history.participant.toi_count,
        },
    )
    return history


async def export_participant_report(
    db: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    limit: int,
    ip_address: str | None,
    user_agent: str | None,
) -> bytes:
    """Build the participant-record PDF. The export is audited as an access event."""
    _user, history = await _build_history(db, user_id, limit)
    pdf = build_participant_report_pdf(
        history, generated_by=actor, generated_at=datetime.now(UTC)
    )

    await write_audit(
        db,
        action=AuditAction.CLINICIAN_PARTICIPANT_VIEWED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"clinical:participant:{user_id}",
        metadata={
            "mode": "export",
            "format": "pdf",
            "participant_id": str(user_id),
            "triage_count": history.participant.triage_count,
            "toi_count": history.participant.toi_count,
        },
    )
    return pdf
