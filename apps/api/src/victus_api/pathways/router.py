"""Pathway entry endpoints.

These endpoints are intentionally thin in the Foundation milestone — they
authenticate, enforce role and consent guards, and emit an audit event
recording the pathway entry. The clinical/ML payloads are added in the
Pathway A (EDL/Triage) and Pathway B (TOI/rPPG) milestones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from victus_api.audit.service import write_audit
from victus_api.core.deps import CurrentUser, DbSession, require_consent, require_role
from victus_api.db.models import AuditAction, ConsentType, UserRole

router = APIRouter(prefix="/pathways", tags=["pathways"])


class PathwayEntryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pathway: Literal["A_TRIAGE", "B_TOI"]
    granted_at: datetime
    next_step: str


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.post(
    "/triage/enter",
    response_model=PathwayEntryResponse,
    summary="Begin a Pathway A (3B-Triage) session. Requires TRIAGE consent.",
)
async def enter_pathway_a(
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser,
        Depends(require_role(UserRole.PATIENT, UserRole.CHW, UserRole.CLINICIAN)),
    ],
    _consent: Annotated[CurrentUser, Depends(require_consent(ConsentType.TRIAGE))],
) -> PathwayEntryResponse:
    ip, ua = _client_metadata(request)
    await write_audit(
        db,
        action=AuditAction.PATHWAY_A_ENTERED,
        actor_id=user.id,
        ip_address=ip,
        user_agent=ua,
        resource="pathway:triage",
    )
    return PathwayEntryResponse(
        pathway="A_TRIAGE",
        granted_at=datetime.now(tz=UTC),
        next_step="/pathways/triage/assess",
    )


@router.post(
    "/toi/enter",
    response_model=PathwayEntryResponse,
    summary="Begin a Pathway B (TOI/rPPG) session. Requires TOI_IMAGING consent.",
)
async def enter_pathway_b(
    request: Request,
    db: DbSession,
    user: Annotated[
        CurrentUser,
        Depends(require_role(UserRole.PATIENT, UserRole.CLINICIAN)),
    ],
    _consent: Annotated[CurrentUser, Depends(require_consent(ConsentType.TOI_IMAGING))],
) -> PathwayEntryResponse:
    ip, ua = _client_metadata(request)
    await write_audit(
        db,
        action=AuditAction.PATHWAY_B_ENTERED,
        actor_id=user.id,
        ip_address=ip,
        user_agent=ua,
        resource="pathway:toi",
    )
    return PathwayEntryResponse(
        pathway="B_TOI",
        granted_at=datetime.now(tz=UTC),
        next_step="/pathways/toi/capture",
    )
