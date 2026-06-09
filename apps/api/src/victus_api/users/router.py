"""Users HTTP layer."""

from __future__ import annotations

from fastapi import APIRouter, Request

from victus_api.auth.schemas import UserPublic
from victus_api.core.deps import CurrentUser, DbSession
from victus_api.users.schemas import ConsentUpdateRequest
from victus_api.users.service import update_consents

router = APIRouter(prefix="/users", tags=["users"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.get("/me", response_model=UserPublic, summary="Return the current user's profile.")
async def get_me(user: CurrentUser) -> UserPublic:
    consents = sorted(user.active_consent_types(), key=lambda c: c.value)
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


@router.patch(
    "/me/consents",
    response_model=UserPublic,
    summary="Grant and/or revoke consents; returns the refreshed profile.",
)
async def patch_consents(
    payload: ConsentUpdateRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> UserPublic:
    ip, ua = _client_metadata(request)
    consents = await update_consents(
        db, user=user, payload=payload, ip_address=ip, user_agent=ua
    )
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
