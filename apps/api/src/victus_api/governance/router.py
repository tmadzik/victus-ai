"""Governance HTTP layer — erasure, anonymisation, subject access."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from victus_api.config import Settings, get_settings
from victus_api.core.deps import CurrentUser, DbSession
from victus_api.governance.schemas import (
    AnonymiseSubjectRequest,
    EraseAccountRequest,
    ErasureRequestResponse,
    MyDataSummary,
)
from victus_api.governance.service import (
    anonymise_subject,
    erase_account_self_service,
    list_my_erasure_requests,
    my_data_summary,
)

router = APIRouter(prefix="/governance", tags=["governance"])


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.get(
    "/my-data-summary",
    response_model=MyDataSummary,
    summary=(
        "Subject access (GDPR Article 15 / POPIA section 23) — inventory the "
        "data this account owns + current PII state. Reading this endpoint is "
        "itself audited as DATA_ACCESS_REQUEST_FULFILLED."
    ),
)
async def my_data_summary_endpoint(
    request: Request,
    db: DbSession,
    user: CurrentUser,
) -> MyDataSummary:
    ip, ua = _client_metadata(request)
    return await my_data_summary(db, user=user, ip_address=ip, user_agent=ua)


@router.post(
    "/erase-account",
    response_model=ErasureRequestResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Erase the authenticated account (GDPR Article 17 / POPIA section "
        "24). Tombstones PII, cascade-anonymises owned study subjects, and "
        "preserves de-identified research data + audit trail under the "
        "statutory research-retention exemption."
    ),
)
async def erase_account_endpoint(
    payload: EraseAccountRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ErasureRequestResponse:
    ip, ua = _client_metadata(request)
    return await erase_account_self_service(
        db,
        user=user,
        payload=payload,
        settings=settings,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/subjects/{subject_id}/anonymise",
    response_model=ErasureRequestResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Anonymise a study subject (typically on participant withdrawal of "
        "consent). Rotates external_subject_id via salted SHA-256, clears "
        "medical history + anthropometrics, retains de-identified sessions."
    ),
)
async def anonymise_subject_endpoint(
    subject_id: uuid.UUID,
    payload: AnonymiseSubjectRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ErasureRequestResponse:
    ip, ua = _client_metadata(request)
    return await anonymise_subject(
        db,
        user=user,
        subject_id=subject_id,
        payload=payload,
        settings=settings,
        ip_address=ip,
        user_agent=ua,
    )


@router.get(
    "/erasure-requests/me",
    response_model=list[ErasureRequestResponse],
    summary="Historical erasure-request audit ledger for this account.",
)
async def list_my_erasure_requests_endpoint(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ErasureRequestResponse]:
    return await list_my_erasure_requests(db, user_id=user.id, limit=limit)
