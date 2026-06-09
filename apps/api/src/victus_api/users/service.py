"""Users domain service — consent management."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.db.models import AuditAction, ConsentRecord, ConsentType, User
from victus_api.users.schemas import ConsentUpdateRequest


async def update_consents(
    db: AsyncSession,
    *,
    user: User,
    payload: ConsentUpdateRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> list[ConsentType]:
    now = datetime.now(tz=UTC)

    if payload.revokes:
        stmt = (
            select(ConsentRecord)
            .where(ConsentRecord.user_id == user.id)
            .where(ConsentRecord.consent_type.in_(payload.revokes))
            .where(ConsentRecord.revoked_at.is_(None))
        )
        for record in (await db.scalars(stmt)).all():
            record.revoked_at = now
            await write_audit(
                db,
                action=AuditAction.CONSENT_REVOKED,
                actor_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"consent_type": record.consent_type.value, "version": record.version},
            )

    for consent_type in payload.grants:
        # Match any prior record for this (user, type, version) regardless of
        # revoked state — the unique constraint covers all three columns, so a
        # previously-revoked row must be REACTIVATED rather than re-inserted.
        existing = await db.scalar(
            select(ConsentRecord)
            .where(ConsentRecord.user_id == user.id)
            .where(ConsentRecord.consent_type == consent_type)
            .where(ConsentRecord.version == payload.version)
        )
        if existing is not None and existing.revoked_at is None:
            continue  # already actively granted — idempotent no-op
        if existing is not None:
            existing.revoked_at = None
            existing.granted_at = now
        else:
            db.add(
                ConsentRecord(
                    user_id=user.id,
                    consent_type=consent_type,
                    version=payload.version,
                )
            )
        await write_audit(
            db,
            action=AuditAction.CONSENT_GRANTED,
            actor_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"consent_type": consent_type.value, "version": payload.version},
        )

    await db.flush()

    stmt = (
        select(ConsentRecord)
        .where(ConsentRecord.user_id == user.id)
        .where(ConsentRecord.revoked_at.is_(None))
    )
    rows = (await db.scalars(stmt)).all()
    return sorted({r.consent_type for r in rows}, key=lambda c: c.value)
