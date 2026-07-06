"""Referral HTTP layer.

Creation and status changes are restricted to CHW / CLINICIAN / ADMIN (the
people who direct care); participants may read their own referrals via /me.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from victus_api.config import Settings, get_settings
from victus_api.core.deps import CurrentUser, DbSession, require_role
from victus_api.db.models import UserRole
from victus_api.referrals.schemas import (
    CreateReferralRequest,
    RecordReferralOutcomeRequest,
    ReferralResponse,
    UpdateReferralStatusRequest,
)
from victus_api.referrals.service import (
    create_referral,
    list_my_referrals,
    list_referrals_for_participant,
    record_referral_outcome,
    update_referral_status,
)

router = APIRouter(prefix="/referrals", tags=["referrals"])

ReferrerUser = Annotated[
    CurrentUser,
    Depends(require_role(UserRole.CHW, UserRole.CLINICIAN, UserRole.ADMIN)),
]


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.post(
    "",
    response_model=ReferralResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Raise a referral for a participant (CHW/clinician/admin).",
)
async def create_endpoint(
    db: DbSession,
    user: ReferrerUser,
    request: Request,
    payload: CreateReferralRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReferralResponse:
    ip, ua = _client_metadata(request)
    return await create_referral(
        db, actor=user, settings=settings, payload=payload, ip_address=ip, user_agent=ua
    )


@router.get(
    "/me",
    response_model=list[ReferralResponse],
    summary="List the authenticated user's own referrals.",
)
async def my_referrals_endpoint(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[ReferralResponse]:
    return await list_my_referrals(db, user_id=user.id, limit=limit)


@router.get(
    "/participant/{user_id}",
    response_model=list[ReferralResponse],
    summary="List a participant's referrals (CHW/clinician/admin).",
)
async def participant_referrals_endpoint(
    db: DbSession,
    user: ReferrerUser,
    user_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ReferralResponse]:
    return await list_referrals_for_participant(db, user_id=user_id, limit=limit)


@router.patch(
    "/{referral_id}/status",
    response_model=ReferralResponse,
    summary="Update a referral's status (CHW/clinician/admin).",
)
async def update_status_endpoint(
    db: DbSession,
    user: ReferrerUser,
    request: Request,
    referral_id: uuid.UUID,
    payload: UpdateReferralStatusRequest,
) -> ReferralResponse:
    ip, ua = _client_metadata(request)
    return await update_referral_status(
        db,
        actor=user,
        referral_id=referral_id,
        payload=payload,
        ip_address=ip,
        user_agent=ua,
    )


@router.patch(
    "/{referral_id}/outcome",
    response_model=ReferralResponse,
    summary="Record a referral's facility outcome — closes the care loop.",
)
async def record_outcome_endpoint(
    db: DbSession,
    user: ReferrerUser,
    request: Request,
    referral_id: uuid.UUID,
    payload: RecordReferralOutcomeRequest,
) -> ReferralResponse:
    ip, ua = _client_metadata(request)
    return await record_referral_outcome(
        db,
        actor=user,
        referral_id=referral_id,
        payload=payload,
        ip_address=ip,
        user_agent=ua,
    )
