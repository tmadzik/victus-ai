"""Pydantic DTOs for the users domain."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from victus_api.db.models import ConsentType

CONSENT_VERSION = "1.0.0"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConsentUpdateRequest(_Base):
    grants: list[ConsentType] = Field(default_factory=list)
    revokes: list[ConsentType] = Field(default_factory=list)
    version: str = Field(default=CONSENT_VERSION, max_length=32)
