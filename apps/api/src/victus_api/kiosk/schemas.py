"""Kiosk gateway DTOs.

Request/response contracts for the device-facing session+capture endpoints and
the public OTP-gated result portal. The encrypted-at-rest result is modelled by
``KioskResultPayload`` — the exact JSON that gets sealed and, on a successful
unlock, handed back to the portal view.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

from victus_api.db.models import TriageState

# Non-diagnostic framing carried with every result, mirroring the WhatsApp /
# TOI consent copy ("wellness screening, not a medical diagnosis").
DEFAULT_DISCLAIMER = (
    "This is a wellness screening, not a medical diagnosis. If you feel unwell "
    "or are worried about your health, please see a healthcare professional."
)


# --- device: session lifecycle ----------------------------------------------


class KioskSessionResponse(BaseModel):
    """Returned to the terminal on session creation — drives the QR display."""

    id: uuid.UUID
    status: str
    site_code: str
    # The single-use code the terminal renders / embeds in the WhatsApp link.
    verification_nonce: str
    # Pre-filled WhatsApp message text the participant sends to link their phone.
    qr_text: str
    # Full wa.me deep link (present when the WhatsApp number is configured).
    whatsapp_deep_link: str | None
    expires_at: datetime
    created_at: datetime


class KioskSessionStatusResponse(BaseModel):
    """Polled by the terminal to learn when to start / has finished capture."""

    id: uuid.UUID
    status: str
    linked: bool
    consented: bool
    result_ready: bool
    expires_at: datetime


# --- device: capture finalisation -------------------------------------------


class KioskCaptureRequest(BaseModel):
    """Derived signals from the in-browser capture — never raw frames.

    The terminal extracts the rPPG traces and quality scalars locally and posts
    only those; ``rppg_signal`` carries the channel traces for the worker to run
    the CHROM/POS pipeline server-side.
    """

    signal_quality_index: Annotated[float, Field(ge=0, le=1)] | None = None
    illumination_score: Annotated[float, Field(ge=0, le=1)] | None = None
    face_bbox_ratio: Annotated[float, Field(ge=0, le=1)] | None = None
    frame_count: Annotated[int, Field(ge=0)] = 0
    error_flags: list[Annotated[str, Field(max_length=64)]] = Field(
        default_factory=list, max_length=32
    )
    # Extracted rPPG traces / intake the worker needs; opaque to this layer.
    rppg_signal: dict[str, Any] | None = None


class KioskCaptureResponse(BaseModel):
    id: uuid.UUID
    status: str
    processing_job_id: uuid.UUID | None


# --- public: OTP-gated result portal ----------------------------------------


class KioskResultPayload(BaseModel):
    """The clinical-triage summary that is sealed at rest and shown on unlock."""

    schema_version: int = 1
    triage_state: TriageState | None = None
    headline: str
    body: str
    vitals: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = DEFAULT_DISCLAIMER
    generated_at: datetime


class KioskResultGateResponse(BaseModel):
    """Pre-unlock probe: confirms the link is live without leaking any data."""

    requires_otp: bool = True
    expires_at: datetime
    locked: bool
    attempts_remaining: int


class ResultUnlockRequest(BaseModel):
    # Exactly four digits; the bounded attempt counter does the real defending.
    otp: Annotated[str, Field(pattern=r"^\d{4}$")]
