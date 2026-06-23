"""Pydantic v2 DTOs for the governance domain."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ErasureJurisdiction(str, enum.Enum):
    GDPR = "GDPR"
    POPIA = "POPIA"
    NDPA = "NDPA"  # Nigeria Data Protection Act 2023 (regulator: NDPC)
    CDPA = "CDPA"  # Zimbabwe Cyber and Data Protection Act [Ch 12:07] (POTRAZ)
    OTHER = "OTHER"


class ErasureBasis(str, enum.Enum):
    DATA_SUBJECT_REQUEST = "DATA_SUBJECT_REQUEST"
    WITHDRAWN_CONSENT = "WITHDRAWN_CONSENT"
    ACCOUNT_DELETION = "ACCOUNT_DELETION"
    ADMIN_ACTION = "ADMIN_ACTION"


class ErasureTargetType(str, enum.Enum):
    USER_ACCOUNT = "USER_ACCOUNT"
    STUDY_SUBJECT = "STUDY_SUBJECT"
    CALIBRATION_RECORD = "CALIBRATION_RECORD"


class ErasureStatus(str, enum.Enum):
    PENDING = "PENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


# --- Account erasure --------------------------------------------------------


class EraseAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Server compares case-insensitively against the authenticated user's
    # current email. Failing match returns 400 (intentional friction).
    confirm_email: EmailStr
    jurisdiction: ErasureJurisdiction = ErasureJurisdiction.GDPR
    request_basis: ErasureBasis = ErasureBasis.ACCOUNT_DELETION
    notes: str | None = Field(default=None, max_length=2000)


# --- Subject anonymisation --------------------------------------------------


class AnonymiseSubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    jurisdiction: ErasureJurisdiction = ErasureJurisdiction.POPIA
    request_basis: ErasureBasis = ErasureBasis.WITHDRAWN_CONSENT
    notes: str | None = Field(default=None, max_length=2000)


# --- Responses --------------------------------------------------------------


class ErasureRequestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    target_type: ErasureTargetType
    target_id: uuid.UUID
    jurisdiction: ErasureJurisdiction
    request_basis: ErasureBasis
    requested_at: datetime
    processed_at: datetime | None
    status: ErasureStatus
    statutory_retention_applied: bool
    retention_basis: str | None
    notes: str | None


class DataInventoryCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    triage_assessments: int
    toi_assessments: int
    calibration_records: int
    study_subjects: int
    study_sessions: int
    consent_records: int
    erasure_requests: int


class MyDataSummary(BaseModel):
    """GDPR Article 15 / POPIA section 23 subject access right.

    Returns counts of every entity the authenticated user owns, plus their
    current PII state. The intent is the user can SEE what we hold before
    deciding to erase.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    email: str | None
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    erased_at: datetime | None
    counts: DataInventoryCounts
    retention_policy_summary: str
