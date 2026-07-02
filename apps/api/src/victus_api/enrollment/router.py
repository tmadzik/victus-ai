"""Enrollment HTTP layer — the authenticated participant enrolls themselves."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from victus_api.config import Settings, get_settings
from victus_api.core.deps import CurrentUser, DbSession
from victus_api.enrollment.schemas import (
    EnrollmentRequest,
    EnrollmentStatusResponse,
    ProfileResponse,
)
from victus_api.enrollment.service import enroll, get_enrollment_status

router = APIRouter(prefix="/enrollment", tags=["enrollment"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.get(
    "/status",
    response_model=EnrollmentStatusResponse,
    summary="Whether the current participant has completed enrollment.",
)
async def status_endpoint(
    db: DbSession, user: CurrentUser
) -> EnrollmentStatusResponse:
    return await get_enrollment_status(db, user=user)


@router.post(
    "",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll (capture identified demographics + consent). Idempotent.",
)
async def enroll_endpoint(
    db: DbSession,
    user: CurrentUser,
    request: Request,
    payload: EnrollmentRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProfileResponse:
    ip, ua = _client_metadata(request)
    return await enroll(
        db, user=user, payload=payload, settings=settings, ip_address=ip, user_agent=ua
    )
