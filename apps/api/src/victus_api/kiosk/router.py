"""Kiosk gateway HTTP layer.

Two audiences, two auth models:

* **Terminal endpoints** (``/kiosk/sessions*``) — authenticated by a per-device
  ``X-Kiosk-Id`` + ``X-Kiosk-Token`` pair, fail-closed in production.
* **Public result portal** (``/kiosk/results/*``) — no account; the opaque URL
  token plus the 4-digit OTP are the only credentials. The unlock endpoint
  returns explicit error responses (never raises) on a bad OTP so the bounded
  attempt-counter increment commits.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import ORJSONResponse

from victus_api.config import Settings, get_settings
from victus_api.core.deps import DbSession
from victus_api.core.exceptions import AuthorizationError
from victus_api.kiosk.config import KioskConfig
from victus_api.kiosk.schemas import (
    KioskCaptureRequest,
    KioskCaptureResponse,
    KioskResultGateResponse,
    KioskResultPayload,
    KioskSessionResponse,
    KioskSessionStatusResponse,
    ResultUnlockRequest,
)
from victus_api.kiosk.service import (
    UnlockSuccess,
    create_session,
    finalize_capture,
    get_result_gate,
    get_status,
    unlock_result,
)

router = APIRouter(prefix="/kiosk", tags=["kiosk"])

_config = KioskConfig.from_env()


async def require_kiosk_device(
    settings: Annotated[Settings, Depends(get_settings)],
    x_kiosk_id: Annotated[str | None, Header(alias="X-Kiosk-Id")] = None,
    x_kiosk_token: Annotated[str | None, Header(alias="X-Kiosk-Token")] = None,
) -> str:
    """Authenticate a terminal; returns the validated ``kiosk_id``."""
    # Fail closed: an unprovisioned fleet must not be reachable in production.
    if settings.is_production and not _config.require_device_auth:
        raise AuthorizationError("Kiosk device auth is not configured.")
    if not _config.verify_device(x_kiosk_id, x_kiosk_token):
        raise AuthorizationError("Invalid kiosk device credentials.")
    assert x_kiosk_id is not None  # verify_device guarantees a non-empty id
    return x_kiosk_id


KioskDevice = Annotated[str, Depends(require_kiosk_device)]


# --- terminal endpoints -----------------------------------------------------


@router.post(
    "/sessions",
    response_model=KioskSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a kiosk session and get the QR / WhatsApp deep-link payload.",
)
async def create_session_endpoint(
    db: DbSession,
    kiosk_id: KioskDevice,
    settings: Annotated[Settings, Depends(get_settings)],
) -> KioskSessionResponse:
    return await create_session(
        db, kiosk_id=kiosk_id, settings=settings, config=_config
    )


@router.get(
    "/sessions/{session_id}",
    response_model=KioskSessionStatusResponse,
    summary="Poll a kiosk session's status (linked / consented / result ready).",
)
async def session_status_endpoint(
    db: DbSession,
    kiosk_id: KioskDevice,
    session_id: uuid.UUID,
) -> KioskSessionStatusResponse:
    return await get_status(db, session_id=session_id)


@router.post(
    "/sessions/{session_id}/capture",
    response_model=KioskCaptureResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit derived capture signals; enqueue processing.",
)
async def capture_endpoint(
    db: DbSession,
    kiosk_id: KioskDevice,
    session_id: uuid.UUID,
    payload: KioskCaptureRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> KioskCaptureResponse:
    return await finalize_capture(
        db, session_id=session_id, payload=payload, settings=settings
    )


# --- public result portal ---------------------------------------------------


@router.get(
    "/results/{token}",
    response_model=KioskResultGateResponse,
    summary="Probe a result link (does it exist / how many OTP tries are left).",
)
async def result_gate_endpoint(
    db: DbSession,
    token: str,
) -> KioskResultGateResponse:
    return await get_result_gate(db, token=token)


_UNLOCK_ERRORS = {
    "expired": (status.HTTP_410_GONE, "This result link is invalid or has expired."),
    "consumed": (status.HTTP_409_CONFLICT, "This result has already been viewed."),
    "locked": (
        status.HTTP_403_FORBIDDEN,
        "Too many incorrect codes — this link is now locked.",
    ),
    "invalid_otp": (status.HTTP_401_UNAUTHORIZED, "Incorrect code."),
}


@router.post(
    "/results/{token}/unlock",
    response_model=KioskResultPayload,
    summary="Unlock a result with the 4-digit OTP (single use).",
)
async def unlock_endpoint(
    db: DbSession,
    request: Request,
    token: str,
    payload: ResultUnlockRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> KioskResultPayload | ORJSONResponse:
    result = await unlock_result(db, token=token, otp=payload.otp, settings=settings)
    if isinstance(result, UnlockSuccess):
        return result.payload
    # Failure: return an explicit response (do NOT raise) so the attempt-counter
    # increment from a wrong OTP is committed rather than rolled back.
    http_status, message = _UNLOCK_ERRORS[result.reason]
    body: dict[str, object] = {"error": {"code": result.reason, "message": message}}
    if result.attempts_remaining is not None:
        body["error"]["attempts_remaining"] = result.attempts_remaining
    return ORJSONResponse(status_code=http_status, content=body)
