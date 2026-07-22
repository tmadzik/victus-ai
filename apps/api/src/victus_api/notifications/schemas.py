"""Pydantic v2 DTOs for the notifications domain."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationType(str, enum.Enum):
    """Must stay in lock-step with ``db.models.NotificationType``.

    A member missing here fails ``NotificationResponse`` validation on read,
    which takes down the caller's whole inbox — not just the one row. A test
    asserts the two enums match member-for-member.
    """

    ERASURE_APPROVAL_REQUESTED = "ERASURE_APPROVAL_REQUESTED"
    ERASURE_REQUEST_APPROVED = "ERASURE_REQUEST_APPROVED"
    ERASURE_REQUEST_REJECTED = "ERASURE_REQUEST_REJECTED"
    REFERRAL_RAISED = "REFERRAL_RAISED"
    RISK_TRAJECTORY_RISE = "RISK_TRAJECTORY_RISE"
    GENERIC = "GENERIC"


class NotificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    resource: str | None
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notifications: list[NotificationResponse]
    unread_count: int


class UnreadCountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unread_count: int
