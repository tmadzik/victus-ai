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


class EnrollmentSummary(BaseModel):
    """The participant's enrollment record as a clinician sees it.

    Identifiers captured at enrollment (age band, sex, region, self-reported
    race/ethnicity) plus the governing jurisdiction, granted consents, and the
    salted patient-id hash. After account erasure the direct/special-category
    fields are ``None`` (tombstoned); the de-identified strata remain.
    """

    enrolled: bool
    age_range: str | None = None
    biological_sex: str | None = None
    region: str | None = None
    race_ethnicity: str | None = None
    jurisdiction: str | None = None
    patient_id_hash: str | None = None
    consents: list[str] = []
    enrolled_at: datetime | None = None


class ParticipantHistory(BaseModel):
    """A participant's identified record: summary + both pathways' assessments."""

    participant: ParticipantSummary
    enrollment: EnrollmentSummary
    triage: list[TriageAssessmentResponse]
    toi: list[ToiAssessmentResponse]
