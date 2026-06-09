"""Auth HTTP layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from victus_api.auth.schemas import (
    AuthSession,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
)
from victus_api.auth.service import (
    login_user,
    logout,
    refresh_session,
    register_user,
)
from victus_api.config import Settings, get_settings
from victus_api.core.deps import CurrentUser, DbSession

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.post(
    "/register",
    response_model=AuthSession,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account and return an initial session.",
)
async def register_endpoint(
    payload: RegisterRequest,
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthSession:
    ip, ua = _client_metadata(request)
    return await register_user(db, payload, settings=settings, ip_address=ip, user_agent=ua)


@router.post(
    "/login",
    response_model=AuthSession,
    summary="Exchange credentials for an access + refresh token pair.",
)
async def login_endpoint(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthSession:
    ip, ua = _client_metadata(request)
    return await login_user(db, payload, settings=settings, ip_address=ip, user_agent=ua)


@router.post(
    "/refresh",
    response_model=AuthSession,
    summary="Rotate the refresh token and issue a fresh access token.",
)
async def refresh_endpoint(
    payload: RefreshRequest,
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthSession:
    ip, ua = _client_metadata(request)
    return await refresh_session(db, payload, settings=settings, ip_address=ip, user_agent=ua)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the supplied refresh token (and audit the logout).",
)
async def logout_endpoint(
    payload: LogoutRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> Response:
    ip, ua = _client_metadata(request)
    await logout(
        db,
        user_id=user.id,
        refresh_token=payload.refresh_token,
        ip_address=ip,
        user_agent=ua,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
