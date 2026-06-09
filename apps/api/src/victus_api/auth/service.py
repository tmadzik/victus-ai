"""Auth domain service — registration, login, refresh, logout, all audited."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from victus_api.audit.service import write_audit
from victus_api.auth.schemas import (
    AuthSession,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)
from victus_api.auth.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    password_needs_rehash,
    verify_password,
)
from victus_api.config import Settings
from victus_api.core.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    TokenInvalidError,
)
from victus_api.db.models import AuditAction, ConsentType, RefreshToken, User


async def register_user(
    db: AsyncSession,
    payload: RegisterRequest,
    *,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthSession:
    email_norm = payload.email.lower()
    existing = await db.scalar(select(User).where(User.email == email_norm))
    if existing is not None:
        raise EmailAlreadyRegisteredError("An account with this email already exists.")

    user = User(
        email=email_norm,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.AUTH_REGISTER,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"role": user.role.value},
    )

    tokens = await _issue_token_pair(
        db,
        user=user,
        consents=[],
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return AuthSession(user=_to_public(user, consents=[]), tokens=tokens)


async def login_user(
    db: AsyncSession,
    payload: LoginRequest,
    *,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthSession:
    email_norm = payload.email.lower()
    # Filter on email IS NOT NULL so erased accounts (NULL email) never
    # appear as login candidates — they're invisible to the lookup even
    # though their row survives for FK consistency.
    user = await db.scalar(
        select(User)
        .where(User.email == email_norm, User.email.isnot(None))
        .options(selectinload(User.consents))
    )

    if (
        user is None
        or not user.is_active
        or user.erased_at is not None
        or user.hashed_password is None
        or not verify_password(payload.password, user.hashed_password)
    ):
        await write_audit(
            db,
            action=AuditAction.AUTH_LOGIN_FAILURE,
            actor_id=user.id if user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"email_attempted": email_norm},
        )
        raise InvalidCredentialsError("Invalid email or password.")

    if password_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(payload.password)

    consents = sorted(user.active_consent_types(), key=lambda c: c.value)

    await write_audit(
        db,
        action=AuditAction.AUTH_LOGIN_SUCCESS,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    tokens = await _issue_token_pair(
        db,
        user=user,
        consents=consents,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return AuthSession(user=_to_public(user, consents=consents), tokens=tokens)


async def refresh_session(
    db: AsyncSession,
    payload: RefreshRequest,
    *,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthSession:
    token_hash = hash_refresh_token(payload.refresh_token)
    record = await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .options(selectinload(RefreshToken.user).selectinload(User.consents))
    )
    now = datetime.now(tz=UTC)

    if record is None or record.revoked_at is not None or record.expires_at < now:
        raise TokenInvalidError("Refresh token is invalid or has expired.")

    user = record.user
    if not user.is_active:
        raise TokenInvalidError("Account is inactive.")

    # Rotate: revoke the presented token, issue a fresh pair.
    record.revoked_at = now

    consents = sorted(user.active_consent_types(), key=lambda c: c.value)
    tokens = await _issue_token_pair(
        db,
        user=user,
        consents=consents,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await write_audit(
        db,
        action=AuditAction.AUTH_REFRESH,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return AuthSession(user=_to_public(user, consents=consents), tokens=tokens)


async def logout(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    refresh_token: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    now = datetime.now(tz=UTC)
    if refresh_token:
        token_hash = hash_refresh_token(refresh_token)
        record = await db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if record is not None and record.revoked_at is None:
            record.revoked_at = now

    await write_audit(
        db,
        action=AuditAction.AUTH_LOGOUT,
        actor_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def _issue_token_pair(
    db: AsyncSession,
    *,
    user: User,
    consents: list[ConsentType],
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenPair:
    access_token, _payload = issue_access_token(
        user_id=user.id,
        role=user.role,
        consents=consents,
        settings=settings,
    )
    refresh_token = generate_refresh_token()
    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=datetime.now(tz=UTC) + timedelta(seconds=settings.jwt_refresh_ttl_seconds),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(refresh_record)
    await db.flush()

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",  # noqa: S106 - OAuth token-type label, not a secret
        expires_in=settings.jwt_access_ttl_seconds,
    )


def _to_public(user: User, *, consents: list[ConsentType]) -> UserPublic:
    return UserPublic.model_validate(
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "consents": consents,
        }
    )
