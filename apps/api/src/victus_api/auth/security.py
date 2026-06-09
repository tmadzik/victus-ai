"""Password hashing, token generation, and JWT signing.

- Password hashing: argon2id with conservative defaults (OWASP recommended).
- Access tokens: short-lived (15 min default) JWTs carrying ``sub`` (user id),
  ``role``, and ``consents``.
- Refresh tokens: opaque 256-bit URL-safe randoms; we store SHA-256 hashes so a
  database leak does not expose live tokens. Tokens rotate on every refresh.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

from victus_api.config import Settings
from victus_api.core.exceptions import TokenExpiredError, TokenInvalidError
from victus_api.db.models import ConsentType, UserRole

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plaintext: str) -> str:
    return _password_hasher.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        _password_hasher.verify(hashed, plaintext)
    except (
        argon2_exceptions.VerifyMismatchError,
        argon2_exceptions.InvalidHashError,
        argon2_exceptions.VerificationError,
    ):
        return False
    return True


def password_needs_rehash(hashed: str) -> bool:
    return _password_hasher.check_needs_rehash(hashed)


@dataclass(frozen=True, slots=True)
class AccessTokenPayload:
    sub: uuid.UUID
    role: UserRole
    consents: tuple[ConsentType, ...]
    iat: datetime
    exp: datetime
    jti: str


def issue_access_token(
    *,
    user_id: uuid.UUID,
    role: UserRole,
    consents: list[ConsentType],
    settings: Settings,
) -> tuple[str, AccessTokenPayload]:
    now = datetime.now(tz=UTC)
    exp = now + timedelta(seconds=settings.jwt_access_ttl_seconds)
    jti = uuid.uuid4().hex

    payload: dict[str, object] = {
        "sub": str(user_id),
        "role": role.value,
        "consents": [c.value for c in consents],
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "typ": "access",
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, AccessTokenPayload(
        sub=user_id,
        role=role,
        consents=tuple(consents),
        iat=now,
        exp=exp,
        jti=jti,
    )


def decode_access_token(token: str, settings: Settings) -> AccessTokenPayload:
    try:
        decoded = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "jti", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError("Access token is invalid.") from exc

    if decoded.get("typ") != "access":
        raise TokenInvalidError("Token type is not 'access'.")

    try:
        sub = uuid.UUID(str(decoded["sub"]))
        role = UserRole(decoded["role"])
        consents = tuple(ConsentType(c) for c in decoded.get("consents", []))
    except (ValueError, KeyError) as exc:
        raise TokenInvalidError("Access token claims are malformed.") from exc

    return AccessTokenPayload(
        sub=sub,
        role=role,
        consents=consents,
        iat=datetime.fromtimestamp(decoded["iat"], tz=UTC),
        exp=datetime.fromtimestamp(decoded["exp"], tz=UTC),
        jti=decoded["jti"],
    )


def generate_refresh_token() -> str:
    """Return a 256-bit cryptographically random URL-safe token."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
