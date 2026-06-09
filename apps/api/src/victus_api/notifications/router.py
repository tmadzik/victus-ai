"""Notifications HTTP layer — every authenticated user sees their own."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from victus_api.core.deps import CurrentUser, DbSession
from victus_api.core.exceptions import NotFoundError
from victus_api.notifications.schemas import (
    NotificationListResponse,
    UnreadCountResponse,
)
from victus_api.notifications.service import (
    list_for_user,
    mark_all_read,
    mark_read,
    unread_count,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "/me",
    response_model=NotificationListResponse,
    summary="List the authenticated user's notifications (newest first).",
)
async def list_endpoint(
    db: DbSession,
    user: CurrentUser,
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotificationListResponse:
    return await list_for_user(
        db, user_id=user.id, unread_only=unread_only, limit=limit
    )


@router.get(
    "/me/unread-count",
    response_model=UnreadCountResponse,
    summary="Unread notification count for the header bell badge.",
)
async def unread_count_endpoint(
    db: DbSession,
    user: CurrentUser,
) -> UnreadCountResponse:
    return await unread_count(db, user_id=user.id)


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a single notification read (scoped to the caller).",
)
async def mark_read_endpoint(
    notification_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> Response:
    ok = await mark_read(db, user_id=user.id, notification_id=notification_id)
    if not ok:
        raise NotFoundError("Notification not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/read-all",
    response_model=UnreadCountResponse,
    summary="Mark all of the caller's notifications read.",
)
async def mark_all_read_endpoint(
    db: DbSession,
    user: CurrentUser,
) -> UnreadCountResponse:
    await mark_all_read(db, user_id=user.id)
    return UnreadCountResponse(unread_count=0)
