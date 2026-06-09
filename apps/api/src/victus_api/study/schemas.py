"""Pydantic v2 DTOs for the study (pre-registration) domain."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from victus_api.toi.schemas import FitzpatrickScale


class SexAtBirth(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    INTERSEX = "INTERSEX"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


class Posture(str, enum.Enum):
    SITTING = "SITTING"
    STANDING = "STANDING"
    SUPINE = "SUPINE"
    SEMI_RECLINED = "SEMI_RECLINED"


class TimeOfDay(str, enum.Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    NIGHT = "NIGHT"


# --- Subject ----------------------------------------------------------------


class CreateSubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_subject_id: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-:.]+$")
    ]
    age_years: Annotated[int, Field(ge=0, le=130)]
    sex_assigned_at_birth: SexAtBirth
    fitzpatrick_scale: FitzpatrickScale | None = None
    height_cm: Annotated[float, Field(gt=0.0, le=250.0)] | None = None
    weight_kg: Annotated[float, Field(gt=0.0, le=400.0)] | None = None
    medical_history_summary: str | None = Field(default=None, max_length=2000)
    consent_protocol_version: str | None = Field(default=None, max_length=64)


class StudySubjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    external_subject_id: str
    age_years: int
    sex_assigned_at_birth: SexAtBirth
    fitzpatrick_scale: FitzpatrickScale | None
    height_cm: float | None
    weight_kg: float | None
    medical_history_summary: str | None
    consent_protocol_version: str
    enrolled_at: datetime
    is_active: bool
    session_count: int = 0
    pair_count: int = 0


# --- Session ----------------------------------------------------------------


class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    study_subject_id: uuid.UUID
    posture: Posture
    # ``None`` defers the choice to the server, which derives it from the
    # current UTC time. Researchers can still override with a specific bucket.
    time_of_day: TimeOfDay | None = None
    ambient_lux: Annotated[float, Field(ge=0.0, le=200_000.0)] | None = None
    ambient_temperature_c: Annotated[float, Field(ge=-20.0, le=60.0)] | None = None
    room_humidity_pct: Annotated[float, Field(ge=0.0, le=100.0)] | None = None
    fasted_hours: Annotated[float, Field(ge=0.0, le=72.0)] | None = None
    caffeine_within_2h: bool = False
    nicotine_within_2h: bool = False
    alcohol_within_24h: bool = False
    last_exercise_hours_ago: Annotated[float, Field(ge=0.0, le=168.0)] | None = None
    recording_site_label: str | None = Field(default=None, max_length=120)
    protocol_version: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)


class StudySessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    study_subject_id: uuid.UUID
    external_subject_id: str
    session_started_at: datetime
    posture: Posture
    time_of_day: TimeOfDay
    ambient_lux: float | None
    ambient_temperature_c: float | None
    room_humidity_pct: float | None
    fasted_hours: float | None
    caffeine_within_2h: bool
    nicotine_within_2h: bool
    alcohol_within_24h: bool
    last_exercise_hours_ago: float | None
    recording_site_label: str | None
    protocol_version: str
    notes: str | None
    is_locked: bool
    locked_at: datetime | None
    ended_at: datetime | None
    pair_count: int = 0


class EndSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=2000)
