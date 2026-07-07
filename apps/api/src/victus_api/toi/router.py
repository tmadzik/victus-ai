"""Pathway B HTTP layer — TOI assessment + history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from victus_api.core.deps import CurrentUser, DbSession, require_consent, require_role
from victus_api.db.models import ConsentType, UserRole
from victus_api.toi.schemas import (
    ToiAssessmentRequest,
    ToiAssessmentResponse,
    ToiTrajectoryResponse,
)
from victus_api.toi.service import (
    assess_toi,
    list_assessments_for_user,
    toi_trajectory_for_user,
)

router = APIRouter(prefix="/pathways/toi", tags=["pathway-b-toi"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.post(
    "/assess",
    response_model=ToiAssessmentResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Run the Pathway B rPPG pipeline on a browser-captured RGB frame series. "
        "CHROM + POS chrominance with auto method selection by SNR, HR/RR/HRV "
        "+ stress proxy, quality gating into GOOD/DEGRADED/POOR."
    ),
)
async def assess_endpoint(
    payload: ToiAssessmentRequest,
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> ToiAssessmentResponse:
    ip, ua = _client_metadata(request)
    return await assess_toi(
        db, user=user, payload=payload, ip_address=ip, user_agent=ua
    )


@router.get(
    "/assessments/me",
    response_model=list[ToiAssessmentResponse],
    summary="List recent TOI assessments for the authenticated user.",
)
async def list_my_assessments(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[ToiAssessmentResponse]:
    return await list_assessments_for_user(db, user_id=user.id, limit=limit)


@router.get(
    "/trajectory/me",
    response_model=ToiTrajectoryResponse,
    summary="The authenticated user's longitudinal contactless vital-sign trend.",
)
async def my_toi_trajectory(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
    limit: Annotated[int, Query(ge=2, le=100)] = 50,
) -> ToiTrajectoryResponse:
    return await toi_trajectory_for_user(db, user_id=user.id, limit=limit)


@router.get(
    "/trajectory/participant/{user_id}",
    response_model=ToiTrajectoryResponse,
    summary="A participant's contactless vital-sign trajectory (clinician/admin).",
)
async def participant_toi_trajectory(
    db: DbSession,
    _user: Annotated[
        CurrentUser, Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN))
    ],
    user_id: uuid.UUID,
    limit: Annotated[int, Query(ge=2, le=100)] = 50,
) -> ToiTrajectoryResponse:
    return await toi_trajectory_for_user(db, user_id=user_id, limit=limit)
