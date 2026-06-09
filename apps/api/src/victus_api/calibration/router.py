"""Calibration HTTP layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from victus_api.calibration.schemas import (
    CalibrationRecordResponse,
    CalibrationStatsResponse,
    RecordCalibrationRequest,
)
from victus_api.calibration.service import (
    calibration_stats,
    export_csv,
    list_calibration_records,
    record_calibration_pair,
)
from victus_api.core.deps import CurrentUser, DbSession, require_consent, require_role
from victus_api.db.models import ConsentType, UserRole

router = APIRouter(prefix="/calibration", tags=["calibration"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.post(
    "/record",
    response_model=CalibrationRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Record a calibration pair: link a completed TOI assessment to an "
        "independent reference-device reading (pulse oximeter, smart watch, "
        "ECG strap, manual pulse count)."
    ),
)
async def record_endpoint(
    payload: RecordCalibrationRequest,
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> CalibrationRecordResponse:
    ip, ua = _client_metadata(request)
    return await record_calibration_pair(
        db, user=user, payload=payload, ip_address=ip, user_agent=ua
    )


@router.get(
    "/stats",
    response_model=CalibrationStatsResponse,
    summary="Bland-Altman + agreement statistics for the user's calibration pairs.",
)
async def stats_endpoint(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> CalibrationStatsResponse:
    return await calibration_stats(db, user_id=user.id)


@router.get(
    "/records",
    response_model=list[CalibrationRecordResponse],
    summary="List recent calibration pairs for the authenticated user.",
)
async def list_endpoint(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[CalibrationRecordResponse]:
    return await list_calibration_records(db, user_id=user.id, limit=limit)


@router.get(
    "/export.csv",
    summary="Stream the user's calibration pairs as a CSV for offline analysis.",
)
async def export_endpoint(
    db: DbSession,
    user: Annotated[
        CurrentUser, Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN))
    ],
    _consent: Annotated[
        CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))
    ],
) -> StreamingResponse:
    return StreamingResponse(
        export_csv(db, user_id=user.id),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="victus-rppg-calibration.csv"'
            ),
        },
    )
