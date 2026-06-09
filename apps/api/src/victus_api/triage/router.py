"""Pathway A HTTP layer — assessment + history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from victus_api.core.deps import CurrentUser, DbSession, require_consent, require_role
from victus_api.db.models import ConsentType, UserRole
from victus_api.triage.schemas import (
    TriageAssessmentRequest,
    TriageAssessmentResponse,
)
from victus_api.triage.service import assess_triage, list_assessments_for_user

router = APIRouter(prefix="/pathways/triage", tags=["pathway-a-triage"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.post(
    "/assess",
    response_model=TriageAssessmentResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Run the Pathway A 3B-Triage assessment. Applies deterministic safety "
        "overrides, plausibility checks, and the EDL inference pipeline."
    ),
)
async def assess_endpoint(
    payload: TriageAssessmentRequest,
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser,
        Depends(require_role(UserRole.PATIENT, UserRole.CHW, UserRole.CLINICIAN)),
    ],
    _consent: Annotated[CurrentUser, Depends(require_consent(ConsentType.TRIAGE))],
) -> TriageAssessmentResponse:
    ip, ua = _client_metadata(request)
    return await assess_triage(
        db, user=user, payload=payload, ip_address=ip, user_agent=ua
    )


@router.get(
    "/assessments/me",
    response_model=list[TriageAssessmentResponse],
    summary="List recent triage assessments for the authenticated user.",
)
async def list_my_assessments(
    db: DbSession,
    user: Annotated[
        CurrentUser,
        Depends(require_role(UserRole.PATIENT, UserRole.CHW, UserRole.CLINICIAN)),
    ],
    _consent: Annotated[CurrentUser, Depends(require_consent(ConsentType.TRIAGE))],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[TriageAssessmentResponse]:
    return await list_assessments_for_user(db, user_id=user.id, limit=limit)
