"""Notifications service — fan-out, list, mark-read, unread-count."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.config import Settings
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    Notification,
    User,
    UserRole,
)
from victus_api.db.models import (
    NotificationType as DbNotificationType,
)
from victus_api.db.session import register_post_commit
from victus_api.notifications.dispatcher import build_slack_payload, dispatch_webhook
from victus_api.notifications.schemas import (
    NotificationListResponse,
    NotificationResponse,
    NotificationType,
    UnreadCountResponse,
)

log = get_logger(__name__)


def _enqueue_webhook(
    db: AsyncSession,
    *,
    settings: Settings,
    type_: NotificationType,
    title: str,
    body: str,
    resource_path: str | None,
    webhook_fields: dict[str, str] | None,
) -> bool:
    """Defer the Slack-compatible webhook POST until AFTER the transaction
    commits, so it never announces an action that then rolls back.

    Returns True if a webhook was enqueued (i.e. a URL is configured), else
    False. The payload is fully materialised now (it does not touch the
    session), and the actual POST runs fire-and-forget post-commit.
    """
    if not settings.notify_webhook_url:
        return False

    link_url = (
        f"{settings.web_app_base_url.rstrip('/')}{resource_path}"
        if resource_path
        else None
    )
    slack_payload = build_slack_payload(
        title=title, body=body, link_url=link_url, fields=webhook_fields
    )
    webhook_url = settings.notify_webhook_url
    timeout_s = settings.notify_webhook_timeout_s

    async def _send() -> None:
        delivered = await dispatch_webhook(
            webhook_url=webhook_url, payload=slack_payload, timeout_s=timeout_s
        )
        log.info(
            "notify_webhook_post_commit",
            type=type_.value,
            delivered=delivered,
        )

    register_post_commit(db, _send)
    return True


async def create_notification(
    db: AsyncSession,
    *,
    recipient_user_id: uuid.UUID,
    type_: NotificationType,
    title: str,
    body: str,
    resource: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Notification:
    row = Notification(
        recipient_user_id=recipient_user_id,
        type=DbNotificationType(type_.value),
        title=title[:255],
        body=body[:2000],
        resource=resource,
        payload=payload or {},
    )
    db.add(row)
    await db.flush()
    return row


async def _active_admin_ids(
    db: AsyncSession, *, exclude_user_id: uuid.UUID | None
) -> list[uuid.UUID]:
    stmt = select(User.id).where(
        User.role == UserRole.ADMIN,
        User.is_active.is_(True),
        User.erased_at.is_(None),
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return list((await db.scalars(stmt)).all())


async def fan_out_to_admins(
    db: AsyncSession,
    *,
    settings: Settings,
    type_: NotificationType,
    title: str,
    body: str,
    resource_path: str | None,
    payload: dict[str, Any] | None,
    exclude_user_id: uuid.UUID | None,
    webhook_fields: dict[str, str] | None = None,
) -> int:
    """Create an in-app notification for every eligible admin and (best-effort)
    POST a single summary to the configured webhook.

    Returns the number of in-app notifications created. The webhook outcome is
    intentionally not surfaced — its failure must not affect the caller.
    """
    admin_ids = await _active_admin_ids(db, exclude_user_id=exclude_user_id)
    for admin_id in admin_ids:
        await create_notification(
            db,
            recipient_user_id=admin_id,
            type_=type_,
            title=title,
            body=body,
            resource=resource_path,
            payload=payload,
        )

    # Webhook is deferred to post-commit (single summary for the admin group).
    enqueued = _enqueue_webhook(
        db,
        settings=settings,
        type_=type_,
        title=title,
        body=body,
        resource_path=resource_path,
        webhook_fields=webhook_fields,
    )

    log.info(
        "notifications_fanned_out",
        type=type_.value,
        in_app_recipients=len(admin_ids),
        webhook_enqueued=enqueued,
    )
    return len(admin_ids)


async def notify_user(
    db: AsyncSession,
    *,
    settings: Settings,
    recipient_user_id: uuid.UUID,
    type_: NotificationType,
    title: str,
    body: str,
    resource_path: str | None,
    payload: dict[str, Any] | None,
    webhook_fields: dict[str, str] | None = None,
) -> None:
    """Create one in-app notification for a single recipient and (best-effort)
    POST a webhook summary. Mirrors :func:`fan_out_to_admins` but for a
    targeted user (e.g. notifying the maker of an approval outcome).
    """
    await create_notification(
        db,
        recipient_user_id=recipient_user_id,
        type_=type_,
        title=title,
        body=body,
        resource=resource_path,
        payload=payload,
    )

    enqueued = _enqueue_webhook(
        db,
        settings=settings,
        type_=type_,
        title=title,
        body=body,
        resource_path=resource_path,
        webhook_fields=webhook_fields,
    )
    log.info(
        "notification_sent",
        type=type_.value,
        recipient_user_id=str(recipient_user_id),
        webhook_enqueued=enqueued,
    )


async def list_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    unread_only: bool = False,
    limit: int = 50,
) -> NotificationListResponse:
    stmt = (
        select(Notification)
        .where(Notification.recipient_user_id == user_id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = (await db.scalars(stmt)).all()
    unread = await _unread_count(db, user_id=user_id)
    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(r) for r in rows],
        unread_count=unread,
    )


async def unread_count(
    db: AsyncSession, *, user_id: uuid.UUID
) -> UnreadCountResponse:
    return UnreadCountResponse(unread_count=await _unread_count(db, user_id=user_id))


async def mark_read(
    db: AsyncSession, *, user_id: uuid.UUID, notification_id: uuid.UUID
) -> bool:
    """Mark one notification read. Returns True if a row was updated.

    Scoped to ``user_id`` so a user cannot mark someone else's notification.
    Idempotent — already-read rows are left untouched and still return True.
    """
    result = await db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.recipient_user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(tz=UTC))
    )
    if result.rowcount and result.rowcount > 0:
        return True
    # Distinguish "not found" from "already read".
    exists = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.id == notification_id,
            Notification.recipient_user_id == user_id,
        )
    )
    return bool(exists)


async def mark_all_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.recipient_user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(tz=UTC))
    )
    return int(result.rowcount or 0)


async def _unread_count(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.recipient_user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).scalar_one()
    )
