"""ADMIN governance HTTP layer.

Every endpoint requires ``UserRole.ADMIN``. The role guard is enforced
server-side regardless of any client-side nav hiding.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from victus_api.config import Settings, get_settings
from victus_api.core.deps import CurrentUser, DbSession, require_role
from victus_api.db.models import UserRole
from victus_api.governance.admin_schemas import (
    AdminAnonymiseSubjectRequest,
    AdminEraseAccountRequest,
    AdminErasureRequestResponse,
    AdminUserDataSummary,
    AdminUserListResponse,
    AuditLogResponse,
    RejectErasureRequest,
)
from victus_api.governance.admin_service import (
    admin_approve_erasure_request,
    admin_list_erasure_requests,
    admin_list_users,
    admin_propose_anonymise_subject,
    admin_propose_erase_account,
    admin_query_audit_log,
    admin_reject_erasure_request,
    admin_user_data_summary,
)
from victus_api.governance.schemas import ErasureRequestResponse

router = APIRouter(prefix="/governance/admin", tags=["governance-admin"])

AdminUser = Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))]


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, (ua[:512] if ua else None)


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="Platform-wide user list with PII state + record counts (admin).",
)
async def list_users_endpoint(
    db: DbSession,
    _admin: AdminUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_erased: Annotated[bool, Query()] = True,
) -> AdminUserListResponse:
    return await admin_list_users(
        db, limit=limit, offset=offset, include_erased=include_erased
    )


@router.get(
    "/users/{user_id}/data-summary",
    response_model=AdminUserDataSummary,
    summary="Inventory any user's data (GDPR Art 15 on behalf of). Audited.",
)
async def user_data_summary_endpoint(
    user_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminUser,
) -> AdminUserDataSummary:
    ip, ua = _client_metadata(request)
    return await admin_user_data_summary(
        db, admin=admin, target_user_id=user_id, ip_address=ip, user_agent=ua
    )


@router.post(
    "/users/{user_id}/erase",
    response_model=ErasureRequestResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "MAKER: propose erasure of another user's account (regulator-forwarded "
        "request). Creates an AWAITING_APPROVAL request — a DIFFERENT admin "
        "must approve before any PII is destroyed."
    ),
)
async def propose_erase_user_endpoint(
    user_id: uuid.UUID,
    payload: AdminEraseAccountRequest,
    request: Request,
    db: DbSession,
    admin: AdminUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ErasureRequestResponse:
    ip, ua = _client_metadata(request)
    return await admin_propose_erase_account(
        db,
        admin=admin,
        target_user_id=user_id,
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
        "MAKER: propose cross-tenant anonymisation of a study subject. "
        "Creates an AWAITING_APPROVAL request requiring a second admin."
    ),
)
async def propose_anonymise_subject_endpoint(
    subject_id: uuid.UUID,
    payload: AdminAnonymiseSubjectRequest,
    request: Request,
    db: DbSession,
    admin: AdminUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ErasureRequestResponse:
    ip, ua = _client_metadata(request)
    return await admin_propose_anonymise_subject(
        db,
        admin=admin,
        subject_id=subject_id,
        payload=payload,
        settings=settings,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/erasure-requests/{request_id}/approve",
    response_model=ErasureRequestResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "CHECKER: approve a pending erasure request and execute it. The "
        "approver must differ from the maker (segregation of duties)."
    ),
)
async def approve_erasure_request_endpoint(
    request_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ErasureRequestResponse:
    ip, ua = _client_metadata(request)
    return await admin_approve_erasure_request(
        db,
        checker=admin,
        request_id=request_id,
        settings=settings,
        ip_address=ip,
        user_agent=ua,
    )


@router.post(
    "/erasure-requests/{request_id}/reject",
    response_model=ErasureRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="CHECKER: reject a pending erasure request. No data is touched.",
)
async def reject_erasure_request_endpoint(
    request_id: uuid.UUID,
    payload: RejectErasureRequest,
    request: Request,
    db: DbSession,
    admin: AdminUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ErasureRequestResponse:
    ip, ua = _client_metadata(request)
    return await admin_reject_erasure_request(
        db,
        checker=admin,
        request_id=request_id,
        reason=payload.reason,
        settings=settings,
        ip_address=ip,
        user_agent=ua,
    )


@router.get(
    "/erasure-requests",
    response_model=list[AdminErasureRequestResponse],
    summary=(
        "Platform-wide erasure ledger with resolved actor/target/approver "
        "emails. Filter by status (e.g. AWAITING_APPROVAL for the queue)."
    ),
)
async def list_erasure_requests_endpoint(
    db: DbSession,
    _admin: AdminUser,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminErasureRequestResponse]:
    return await admin_list_erasure_requests(
        db, status=status_filter, limit=limit, offset=offset
    )


@router.get(
    "/audit-log",
    response_model=AuditLogResponse,
    summary="Query the platform audit log filtered by action and/or actor.",
)
async def audit_log_endpoint(
    db: DbSession,
    _admin: AdminUser,
    action: Annotated[str | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogResponse:
    return await admin_query_audit_log(
        db, action=action, actor_id=actor_id, limit=limit, offset=offset
    )
