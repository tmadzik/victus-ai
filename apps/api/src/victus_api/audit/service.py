"""Audit logging — append-only writes keyed off domain actions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.core.logging import get_logger
from victus_api.db.models import AuditAction, AuditLog

log = get_logger(__name__)


async def write_audit(
    db: AsyncSession,
    *,
    action: AuditAction,
    actor_id: uuid.UUID | None,
    resource: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource=resource,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_json=metadata or {},
    )
    db.add(entry)
    await db.flush()
    log.info(
        "audit_event",
        action=action.value,
        actor_id=str(actor_id) if actor_id else None,
        resource=resource,
    )
    return entry
