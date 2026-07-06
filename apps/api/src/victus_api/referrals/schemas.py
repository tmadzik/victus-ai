"""Referral DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from victus_api.db.models import (
    ReferralDestinationType,
    ReferralOutcome,
    ReferralStatus,
    ReferralUrgency,
)


class CreateReferralRequest(BaseModel):
    participant_user_id: uuid.UUID
    destination_type: ReferralDestinationType
    destination_name: Annotated[str, Field(min_length=1, max_length=200)]
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    urgency: ReferralUrgency
    source_triage_assessment_id: uuid.UUID | None = None
    notes: Annotated[str, Field(max_length=1000)] | None = None


class UpdateReferralStatusRequest(BaseModel):
    status: ReferralStatus
    notes: Annotated[str, Field(max_length=1000)] | None = None


class RecordReferralOutcomeRequest(BaseModel):
    """Close the care loop: the facility-confirmed clinical result."""

    outcome: ReferralOutcome
    notes: Annotated[str, Field(max_length=1000)] | None = None


class ReferralResponse(BaseModel):
    id: uuid.UUID
    participant_user_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    source_triage_assessment_id: uuid.UUID | None
    destination_type: str
    destination_name: str
    reason: str
    urgency: str
    status: str
    notes: str | None
    outcome: str
    outcome_recorded_at: datetime | None
    outcome_notes: str | None
    created_at: datetime
    updated_at: datetime
