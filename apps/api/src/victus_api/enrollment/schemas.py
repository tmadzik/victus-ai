"""Enrollment DTOs.

Adults only: ``AgeRange`` has no under-18 band, so an under-age enrollment
cannot even be expressed. Consent to both pathways is mandatory to enroll.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, model_validator

from victus_api.db.models import SexAtBirth


class AgeRange(str, enum.Enum):
    """Adult age bands (data-minimising alternative to an exact age)."""

    A18_29 = "18-29"
    A30_39 = "30-39"
    A40_49 = "40-49"
    A50_59 = "50-59"
    A60_69 = "60-69"
    A70_PLUS = "70+"


class Region(str, enum.Enum):
    """Enrollment region — drives the governing data-protection jurisdiction."""

    NG = "NG"  # Nigeria → NDPA
    ZW = "ZW"  # Zimbabwe → CDPA
    ZA = "ZA"  # South Africa → POPIA
    OTHER = "OTHER"


class EnrollmentRequest(BaseModel):
    # Direct identifiers (stored, tombstoned on erasure).
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    email: EmailStr
    # Raw external patient/client id — hashed on the server, never stored plain.
    patient_id: Annotated[str, Field(min_length=1, max_length=128)]
    age_range: AgeRange
    biological_sex: SexAtBirth
    region: Region
    # Self-reported, optional; separate from the TOI Fitzpatrick phototype.
    race_ethnicity: Annotated[str, Field(max_length=64)] | None = None
    # Consent — both pathways are mandatory to enroll; research is optional.
    consent_triage: bool
    consent_toi_imaging: bool
    consent_research: bool = False

    @model_validator(mode="after")
    def _require_pathway_consent(self) -> EnrollmentRequest:
        if not (self.consent_triage and self.consent_toi_imaging):
            raise ValueError(
                "Consent to both the triage and TOI-imaging pathways is required "
                "to enroll."
            )
        return self


class EnrollmentStatusResponse(BaseModel):
    """Drives the enrollment gate — is this participant cleared for the app?"""

    enrolled: bool
    has_profile: bool
    missing_consents: list[str]


class ProfileResponse(BaseModel):
    """Identified enrollment record (clinician/admin + the participant's own)."""

    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str | None
    email: str | None
    patient_id_hash: str | None
    age_range: str
    biological_sex: str
    region: str
    race_ethnicity: str | None
    jurisdiction: str
    enrolled_at: datetime
