"""Wire types for the organisation cohort dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AttestationResponse(BaseModel):
    """A recorded care-use declaration."""

    version: str
    attested_at: datetime
    expires_at: datetime


class AttestationStatusResponse(BaseModel):
    """Whether this operator may open individual member results.

    ``text`` rides along so the client never has to hold its own copy of the
    wording — a stale copy in a frontend would mean people agreeing to something
    other than what is recorded against their name.
    """

    active: bool
    version: str
    text: str
    expires_at: datetime | None = None


class CohortResponse(BaseModel):
    """Suppressed cohort aggregates.

    A ``null`` in any breakdown means *suppressed*, not zero. The distinction
    matters: zero says nobody is in that cell, null says too few people are for
    it to be shown. ``suppression`` reports how much was withheld so a thin
    cohort is not mistaken for a biased one.
    """

    members_screened: int
    triage_distribution: dict[str, int | None]
    by_age_band: dict[str, int | None]
    by_sex: dict[str, int | None]
    care_loop: dict[str, Any]
    suppression: dict[str, Any]


class FlaggedMemberResponse(BaseModel):
    user_id: str
    triage_state: str
    assessed_at: str


class FlaggedMemberListResponse(BaseModel):
    """Named members for care routing — the payload the attestation gates."""

    members: list[FlaggedMemberResponse]
    count: int = Field(ge=0)
    attestation_version: str
