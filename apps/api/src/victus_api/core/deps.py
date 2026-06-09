"""FastAPI dependency providers.

`get_current_user` and `require_role` enforce JWT-based authentication and
RBAC. `require_consent` guards pathway entry on explicit user consent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from victus_api.auth.security import decode_access_token
from victus_api.config import Settings, get_settings
from victus_api.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConsentRequiredError,
    TokenInvalidError,
)
from victus_api.db.models import ConsentType, User, UserRole
from victus_api.db.session import get_db as _get_db

bearer_scheme = HTTPBearer(auto_error=False)


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in _get_db():
        yield session


DbSession = Annotated[AsyncSession, Depends(db_session)]


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Missing or malformed Authorization header.")

    payload = decode_access_token(credentials.credentials, settings)
    user_id = payload.sub

    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.consents))
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise TokenInvalidError("User not found or deactivated.")

    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: UserRole) -> Callable[..., Awaitable[User]]:
    """Factory for a dependency that enforces role membership."""

    allowed_set = frozenset(allowed)

    async def _checker(user: CurrentUser) -> User:
        if user.role not in allowed_set:
            raise AuthorizationError(
                f"Role '{user.role.value}' is not permitted for this resource.",
                details={"required_roles": [r.value for r in allowed_set]},
            )
        return user

    return _checker


def require_consent(*required: ConsentType) -> Callable[..., Awaitable[User]]:
    """Factory for a dependency that enforces active consent records."""

    required_set = frozenset(required)

    async def _checker(user: CurrentUser) -> User:
        granted = user.active_consent_types()
        missing = required_set - granted
        if missing:
            raise ConsentRequiredError(
                "Required consent has not been granted.",
                details={"missing_consents": sorted(c.value for c in missing)},
            )
        return user

    return _checker


async def verify_internal_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Guard for service-to-service endpoints called by the Next.js server."""
    expected = settings.internal_service_token.get_secret_value()
    if not x_internal_token or x_internal_token != expected:
        raise AuthorizationError(
            "Invalid internal service token.",
            details={"hint": "This endpoint is for trusted server-to-server calls only."},
        )


__all__ = [
    "CurrentUser",
    "DbSession",
    "bearer_scheme",
    "db_session",
    "get_current_user",
    "require_consent",
    "require_role",
    "status",
    "verify_internal_token",
]
