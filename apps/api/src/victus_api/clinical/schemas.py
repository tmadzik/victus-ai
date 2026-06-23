"""Clinician review DTOs: participant summaries + the merged history view."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from victus_api.toi.schemas import ToiAssessmentResponse
from victus_api.triage.schemas import TriageAssessmentResponse


class ParticipantSummary(BaseModel):
    """A participant as a clinician sees them in search / on the record header."""

    user_id: uuid.UUID
    email: str | None
    full_name: str | None
    role: str
    is_active: bool
    site_code: str
    triage_count: int
    toi_count: int
    last_activity: datetime | None


class ParticipantHistory(BaseModel):
    """A participant's identified record: summary + both pathways' assessments."""

    participant: ParticipantSummary
    triage: list[TriageAssessmentResponse]
    toi: list[ToiAssessmentResponse]
