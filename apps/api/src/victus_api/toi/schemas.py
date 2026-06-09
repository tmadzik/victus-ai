"""Pydantic v2 DTOs for the Pathway B / TOI domain."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToiQuality(str, enum.Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    POOR = "POOR"


class FitzpatrickScale(str, enum.Enum):
    I = "I"  # noqa: E741 - Fitzpatrick type I, a clinical scale label
    II = "II"
    III = "III"
    IV = "IV"
    V = "V"
    VI = "VI"


# Minimum capture parameters — anything tighter fails fast at the API edge.
MIN_CAPTURE_SECONDS = 5.0
MAX_CAPTURE_SECONDS = 60.0
MIN_FRAMES = 100
MAX_FRAMES = 3600  # 60 s × 60 fps headroom


class RppgFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    t_ms: Annotated[int, Field(ge=0, le=120_000)]
    r: Annotated[float, Field(ge=0.0, le=255.0)]
    g: Annotated[float, Field(ge=0.0, le=255.0)]
    b: Annotated[float, Field(ge=0.0, le=255.0)]


class ToiAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: Annotated[list[RppgFrame], Field(min_length=MIN_FRAMES, max_length=MAX_FRAMES)]
    sample_rate_hz: Annotated[float, Field(gt=0.0, le=240.0)]
    duration_s: Annotated[float, Field(ge=MIN_CAPTURE_SECONDS, le=MAX_CAPTURE_SECONDS)]
    skin_tone_estimate: FitzpatrickScale | None = None
    # Client-side quality estimates computed during capture.
    motion_score: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    lighting_score: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    face_presence_ratio: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0


class BiomarkerEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    ci_low: float | None = None
    ci_high: float | None = None
    unit: str
    experimental: bool = False


class SignalQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snr_chrom_db: float
    snr_pos_db: float
    method_selected: Literal["chrom", "pos", "none"]
    motion_score: float
    lighting_score: float
    face_presence_ratio: float
    frames_used: int


class ToiAssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    quality: ToiQuality
    duration_s: float
    sample_rate_hz: float
    frame_count: int
    biomarkers: dict[str, BiomarkerEstimate]
    signal_quality: SignalQuality
    method_details: dict[str, object]
    warnings: list[str]
    next_action: str
    pipeline_version: str
    created_at: datetime
