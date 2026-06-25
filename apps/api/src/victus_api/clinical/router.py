"""Clinician participant-review HTTP layer (CLINICIAN / ADMIN only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from victus_api.clinical.schemas import ParticipantHistory, ParticipantSummary
from victus_api.clinical.service import (
    export_participant_report,
    get_participant_history,
    search_participants,
)
from victus_api.core.deps import CurrentUser, DbSession, require_role
from victus_api.db.models import UserRole

router = APIRouter(prefix="/clinical", tags=["clinical"])

# Viewing another participant's identified record is a clinician/admin action;
# CHWs and patients are excluded. Every access is audited in the service.
ClinicianUser = Annotated[
    CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN))
]


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.get(
    "/participants",
    response_model=list[ParticipantSummary],
    summary="Search participants by email or name (clinician/admin).",
)
async def search_endpoint(
    db: DbSession,
    user: ClinicianUser,
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> list[ParticipantSummary]:
    ip, ua = _client_metadata(request)
    return await search_participants(
        db, actor=user, query=q, limit=limit, ip_address=ip, user_agent=ua
    )


@router.get(
    "/participants/{user_id}/history",
    response_model=ParticipantHistory,
    summary="A participant's identified assessment record (clinician/admin).",
)
async def history_endpoint(
    db: DbSession,
    user: ClinicianUser,
    request: Request,
    user_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ParticipantHistory:
    ip, ua = _client_metadata(request)
    return await get_participant_history(
        db, actor=user, user_id=user_id, limit=limit, ip_address=ip, user_agent=ua
    )


@router.get(
    "/participants/{user_id}/report.pdf",
    response_class=Response,
    summary="Download a participant's record as a PDF (clinician/admin).",
)
async def report_pdf_endpoint(
    db: DbSession,
    user: ClinicianUser,
    request: Request,
    user_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Response:
    ip, ua = _client_metadata(request)
    pdf = await export_participant_report(
        db, actor=user, user_id=user_id, limit=limit, ip_address=ip, user_agent=ua
    )
    filename = f"victus-participant-{str(user_id)[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
