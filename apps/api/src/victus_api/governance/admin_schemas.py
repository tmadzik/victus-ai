"""Pydantic v2 DTOs for ADMIN-initiated governance flows.

These mirror the self-service governance schemas but carry the additional
target/actor context an admin needs to act on behalf of another data
subject, and surface platform-wide views (user list, full audit log).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from victus_api.governance.schemas import (
    DataInventoryCounts,
    ErasureBasis,
    ErasureJurisdiction,
    ErasureStatus,
    ErasureTargetType,
)


class AdminUserListItem(BaseModel):
    """One row of the platform-wide user list (admin-only).

    ``email`` / ``full_name`` are NULL for tombstoned (erased) accounts —
    admins see the de-identified shell, never resurrected PII.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    email: str | None
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    erased_at: datetime | None
    subject_count: int = 0
    calibration_count: int = 0


class AdminUserListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    users: list[AdminUserListItem]
    total: int
    limit: int
    offset: int


class AdminEraseAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # The admin must restate the target's user id in the body as a deliberate
    # confirmation that they are erasing the right person — the path param
    # alone is too easy to fat-finger.
    confirm_user_id: uuid.UUID
    jurisdiction: ErasureJurisdiction = ErasureJurisdiction.GDPR
    request_basis: ErasureBasis = ErasureBasis.ADMIN_ACTION
    notes: str | None = Field(default=None, max_length=2000)


class AdminAnonymiseSubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    jurisdiction: ErasureJurisdiction = ErasureJurisdiction.POPIA
    request_basis: ErasureBasis = ErasureBasis.ADMIN_ACTION
    notes: str | None = Field(default=None, max_length=2000)


class AdminUserDataSummary(BaseModel):
    """Admin view of any user's data inventory (GDPR Art 15 on behalf of)."""

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    email: str | None
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    erased_at: datetime | None
    counts: DataInventoryCounts


class AdminErasureRequestResponse(BaseModel):
    """Platform-wide erasure-ledger row with resolved actor/target labels."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    requesting_actor_user_id: uuid.UUID | None
    requesting_actor_email: str | None
    target_user_id: uuid.UUID | None
    target_user_email: str | None
    target_type: ErasureTargetType
    target_id: uuid.UUID
    jurisdiction: ErasureJurisdiction
    request_basis: ErasureBasis
    requested_at: datetime
    processed_at: datetime | None
    status: ErasureStatus
    statutory_retention_applied: bool
    notes: str | None
    # Maker-checker fields
    requires_approval: bool = False
    approved_by_user_id: uuid.UUID | None = None
    approved_by_email: str | None = None
    approved_at: datetime | None = None
    rejected_by_user_id: uuid.UUID | None = None
    rejected_by_email: str | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None


class RejectErasureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=2000)


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    resource: str | None
    ip_address: str | None
    metadata_json: dict
    created_at: datetime


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[AuditLogEntry]
    total: int
    limit: int
    offset: int


# Query parameter container — validated by FastAPI Query() at the router.
class AuditLogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str | None = None
    actor_id: uuid.UUID | None = None
    limit: Annotated[int, Field(ge=1, le=500)] = 100
    offset: Annotated[int, Field(ge=0)] = 0
