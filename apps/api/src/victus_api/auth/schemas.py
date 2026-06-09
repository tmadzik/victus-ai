"""Pydantic v2 DTOs for the auth domain."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from victus_api.db.models import ConsentType, UserRole

PASSWORD_MIN_LENGTH = 12
_LOWER = re.compile(r"[a-z]")
_UPPER = re.compile(r"[A-Z]")
_DIGIT = re.compile(r"\d")


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        use_enum_values=False,
        extra="forbid",
    )


class RegisterRequest(_Base):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    role: UserRole = UserRole.PATIENT

    @field_validator("password")
    @classmethod
    def _password_complexity(cls, value: str) -> str:
        if not _LOWER.search(value) or not _UPPER.search(value) or not _DIGIT.search(value):
            raise ValueError(
                "Password must contain at least one lowercase letter, "
                "one uppercase letter, and one digit."
            )
        return value


class LoginRequest(_Base):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(_Base):
    refresh_token: str = Field(min_length=20, max_length=512)


class LogoutRequest(_Base):
    refresh_token: str | None = Field(default=None, max_length=512)


class UserPublic(_Base):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    consents: list[ConsentType] = Field(default_factory=list)


class TokenPair(_Base):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"  # noqa: S105 - OAuth token-type label, not a secret
    expires_in: int = Field(description="Access-token TTL in seconds.")


class AuthSession(_Base):
    user: UserPublic
    tokens: TokenPair
