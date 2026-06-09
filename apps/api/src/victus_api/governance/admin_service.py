"""ADMIN-initiated governance service.

Reuses the self-service execution primitives (``_execute_account_erasure``,
``_execute_subject_anonymisation``, ``_count_data``) so the erasure semantics
are identical regardless of who initiates them. Admin-initiated erasures use
maker-checker: one admin proposes (AWAITING_APPROVAL, data untouched), a
DIFFERENT admin approves (executes) or rejects. Every action is doubly
audited — the admin's ``actor_id`` and the target's ``target_user_id``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from victus_api.audit.service import write_audit
from victus_api.config import Settings
from victus_api.core.exceptions import NotFoundError
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    AuditLog,
    ErasureRequest,
    RppgCalibrationRecord,
    StudySubject,
    User,
)
from victus_api.db.models import (
    ErasureStatus as DbErasureStatus,
)
from victus_api.db.models import (
    ErasureTargetType as DbErasureTargetType,
)
from victus_api.governance.admin_schemas import (
    AdminAnonymiseSubjectRequest,
    AdminEraseAccountRequest,
    AdminErasureRequestResponse,
    AdminUserDataSummary,
    AdminUserListItem,
    AdminUserListResponse,
    AuditLogEntry,
    AuditLogResponse,
)
from victus_api.governance.schemas import (
    ErasureBasis,
    ErasureJurisdiction,
    ErasureStatus,
    ErasureTargetType,
)
from victus_api.governance.service import (
    GovernanceError,
    _count_data,
    _create_account_erasure_request,
    _create_subject_anonymisation_request,
    _execute_account_erasure,
    _execute_subject_anonymisation,
)
from victus_api.notifications.schemas import NotificationType
from victus_api.notifications.service import notify_user

# Deep link the outcome notifications point the maker at.
_LEDGER_PATH = "/admin/governance?tab=ledger"


async def _notify_maker_of_outcome(
    db: AsyncSession,
    *,
    settings: Settings,
    req: ErasureRequest,
    decider: User,
    outcome: str,  # "approved" | "rejected"
    reason: str | None = None,
) -> None:
    """Notify the maker that their proposal was approved or rejected.

    No-op when the maker is unknown (FK was SET NULL) — there is nobody to
    notify. The decider is never the maker (segregation of duties), so this
    never self-notifies.
    """
    maker_id = req.requesting_actor_user_id
    if maker_id is None:
        return
    decider_label = decider.email or str(decider.id)
    target_kind = (
        "user account"
        if req.target_type == DbErasureTargetType.USER_ACCOUNT
        else "study subject"
    )
    if outcome == "approved":
        type_ = NotificationType.ERASURE_REQUEST_APPROVED
        title = "Erasure request approved"
        body = (
            f"{decider_label} approved your proposed erasure of a "
            f"{target_kind}. The erasure has been executed."
        )
    else:
        type_ = NotificationType.ERASURE_REQUEST_REJECTED
        title = "Erasure request rejected"
        body = (
            f"{decider_label} rejected your proposed erasure of a "
            f"{target_kind}."
            + (f" Reason: {reason}" if reason else "")
        )
    await notify_user(
        db,
        settings=settings,
        recipient_user_id=maker_id,
        type_=type_,
        title=title,
        body=body,
        resource_path=_LEDGER_PATH,
        payload={
            "erasure_request_id": str(req.id),
            "target_type": req.target_type.value,
            "decider_user_id": str(decider.id),
            "outcome": outcome,
        },
        webhook_fields={
            "Decision": outcome,
            "Decided by": decider_label,
            "Target type": req.target_type.value,
        },
    )

log = get_logger(__name__)


# --- User list / data summary -----------------------------------------------


async def admin_list_users(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    include_erased: bool = True,
) -> AdminUserListResponse:
    base = select(User)
    if not include_erased:
        base = base.where(User.erased_at.is_(None))

    total = int(
        (
            await db.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()
    )

    rows = (
        await db.scalars(
            base.order_by(desc(User.created_at)).limit(limit).offset(offset)
        )
    ).all()

    items: list[AdminUserListItem] = []
    for u in rows:
        subject_count = int(
            (
                await db.execute(
                    select(func.count(StudySubject.id)).where(
                        StudySubject.user_id == u.id
                    )
                )
            ).scalar_one()
        )
        calibration_count = int(
            (
                await db.execute(
                    select(func.count(RppgCalibrationRecord.id)).where(
                        RppgCalibrationRecord.user_id == u.id
                    )
                )
            ).scalar_one()
        )
        items.append(
            AdminUserListItem(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=u.role.value,
                is_active=u.is_active,
                created_at=u.created_at,
                erased_at=u.erased_at,
                subject_count=subject_count,
                calibration_count=calibration_count,
            )
        )

    return AdminUserListResponse(
        users=items, total=total, limit=limit, offset=offset
    )


async def admin_user_data_summary(
    db: AsyncSession,
    *,
    admin: User,
    target_user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> AdminUserDataSummary:
    target = await db.get(User, target_user_id)
    if target is None:
        raise NotFoundError("User not found.")

    counts = await _count_data(db, user_id=target.id)

    await write_audit(
        db,
        action=AuditAction.DATA_ACCESS_REQUEST_FULFILLED,
        actor_id=admin.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:admin:data-summary:{target.id}",
        metadata={
            "target_user_id": str(target.id),
            "actor_kind": "admin",
            **counts.model_dump(),
        },
    )

    return AdminUserDataSummary(
        user_id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=target.role.value,
        is_active=target.is_active,
        created_at=target.created_at,
        erased_at=target.erased_at,
        counts=counts,
    )


# --- Erasure / anonymisation (admin-initiated) ------------------------------


async def _resolve_admin_response(
    db: AsyncSession, req: ErasureRequest
) -> AdminErasureRequestResponse:
    """Build the full admin DTO for a single request — the same shape the
    ledger returns, with actor/target/approver/rejecter emails resolved — so
    the maker-checker endpoints surface attribution (``requires_approval``,
    ``approved_by_*``, ``rejected_by_*``) directly instead of forcing the
    caller to re-query the ledger.
    """

    async def _email(user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        user = await db.get(User, user_id)
        return user.email if user is not None else None

    return AdminErasureRequestResponse(
        id=req.id,
        requesting_actor_user_id=req.requesting_actor_user_id,
        requesting_actor_email=await _email(req.requesting_actor_user_id),
        target_user_id=req.target_user_id,
        target_user_email=await _email(req.target_user_id),
        target_type=ErasureTargetType(req.target_type.value),
        target_id=req.target_id,
        jurisdiction=ErasureJurisdiction(req.jurisdiction.value),
        request_basis=ErasureBasis(req.request_basis.value),
        requested_at=req.requested_at,
        processed_at=req.processed_at,
        status=ErasureStatus(req.status.value),
        statutory_retention_applied=req.statutory_retention_applied,
        notes=req.notes,
        requires_approval=req.requires_approval,
        approved_by_user_id=req.approved_by_user_id,
        approved_by_email=await _email(req.approved_by_user_id),
        approved_at=req.approved_at,
        rejected_by_user_id=req.rejected_by_user_id,
        rejected_by_email=await _email(req.rejected_by_user_id),
        rejected_at=req.rejected_at,
        rejection_reason=req.rejection_reason,
    )


async def admin_propose_erase_account(
    db: AsyncSession,
    *,
    admin: User,
    target_user_id: uuid.UUID,
    payload: AdminEraseAccountRequest,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AdminErasureRequestResponse:
    """Maker step — propose an account erasure for a second admin to approve.

    Creates an AWAITING_APPROVAL request and notifies eligible checkers; the
    target's PII is NOT touched until a different admin approves.
    """
    if payload.confirm_user_id != target_user_id:
        raise GovernanceError(
            "confirm_user_id does not match the path user id; erasure not performed.",
        )
    if target_user_id == admin.id:
        raise GovernanceError(
            "Use the self-service /governance/erase-account endpoint to erase "
            "your own account.",
        )
    target = await db.get(User, target_user_id)
    if target is None:
        raise NotFoundError("User not found.")

    request_row = await _create_account_erasure_request(
        db,
        actor_user=admin,
        target_user=target,
        jurisdiction=payload.jurisdiction,
        request_basis=payload.request_basis,
        notes=payload.notes,
        requires_approval=True,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return await _resolve_admin_response(db, request_row)


async def admin_propose_anonymise_subject(
    db: AsyncSession,
    *,
    admin: User,
    subject_id: uuid.UUID,
    payload: AdminAnonymiseSubjectRequest,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AdminErasureRequestResponse:
    """Maker step — propose a cross-tenant subject anonymisation."""
    subject = await db.get(StudySubject, subject_id)
    if subject is None:
        raise NotFoundError("Study subject not found.")

    request_row = await _create_subject_anonymisation_request(
        db,
        actor_user=admin,
        subject=subject,
        jurisdiction=payload.jurisdiction,
        request_basis=payload.request_basis,
        notes=payload.notes,
        requires_approval=True,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return await _resolve_admin_response(db, request_row)


async def admin_approve_erasure_request(
    db: AsyncSession,
    *,
    checker: User,
    request_id: uuid.UUID,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AdminErasureRequestResponse:
    """Checker step — approve a pending request and execute it.

    Enforces segregation of duties: the approver MUST differ from the maker.
    Dispatches to the correct execution primitive based on ``target_type``.
    """
    req = await db.get(ErasureRequest, request_id)
    if req is None:
        raise NotFoundError("Erasure request not found.")
    if req.status != DbErasureStatus.AWAITING_APPROVAL:
        raise GovernanceError(
            f"Request is not awaiting approval (status={req.status.value}).",
            details={"status": req.status.value},
        )
    if req.requesting_actor_user_id == checker.id:
        raise GovernanceError(
            "Segregation of duties: you cannot approve a request you created. "
            "A different administrator must approve it.",
        )

    # Audit the approval decision BEFORE executing so the ledger records the
    # decision even if execution fails.
    req.approved_by_user_id = checker.id
    req.approved_at = datetime.now(tz=UTC)
    await db.flush()
    await write_audit(
        db,
        action=AuditAction.ERASURE_REQUEST_APPROVED,
        actor_id=checker.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:erasure:{req.id}",
        metadata={
            "erasure_request_id": str(req.id),
            "maker_user_id": str(req.requesting_actor_user_id),
            "target_type": req.target_type.value,
            "target_id": str(req.target_id),
        },
    )

    if req.target_type == DbErasureTargetType.USER_ACCOUNT:
        target = await db.get(User, req.target_id)
        if target is None:
            raise NotFoundError("Target user no longer exists.")
        await _execute_account_erasure(
            db,
            request_row=req,
            executor_user=checker,
            target_user=target,
            settings=settings,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    elif req.target_type == DbErasureTargetType.STUDY_SUBJECT:
        subject = await db.get(StudySubject, req.target_id)
        if subject is None:
            raise NotFoundError("Target subject no longer exists.")
        await _execute_subject_anonymisation(
            db,
            request_row=req,
            executor_user=checker,
            subject=subject,
            settings=settings,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    else:  # pragma: no cover - exhaustiveness guard
        raise GovernanceError(
            f"Unsupported target_type for approval: {req.target_type.value}",
        )

    await _notify_maker_of_outcome(
        db, settings=settings, req=req, decider=checker, outcome="approved"
    )

    log.info(
        "erasure_request_approved",
        erasure_request_id=str(req.id),
        checker_user_id=str(checker.id),
        maker_user_id=str(req.requesting_actor_user_id),
        target_type=req.target_type.value,
    )
    return await _resolve_admin_response(db, req)


async def admin_reject_erasure_request(
    db: AsyncSession,
    *,
    checker: User,
    request_id: uuid.UUID,
    reason: str | None,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AdminErasureRequestResponse:
    """Checker step — reject a pending request. No data is touched."""
    req = await db.get(ErasureRequest, request_id)
    if req is None:
        raise NotFoundError("Erasure request not found.")
    if req.status != DbErasureStatus.AWAITING_APPROVAL:
        raise GovernanceError(
            f"Request is not awaiting approval (status={req.status.value}).",
            details={"status": req.status.value},
        )
    if req.requesting_actor_user_id == checker.id:
        raise GovernanceError(
            "Segregation of duties: you cannot reject a request you created.",
        )

    now = datetime.now(tz=UTC)
    req.status = DbErasureStatus.REJECTED
    req.rejected_by_user_id = checker.id
    req.rejected_at = now
    req.processed_at = now
    req.rejection_reason = reason
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.ERASURE_REQUEST_REJECTED,
        actor_id=checker.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:erasure:{req.id}",
        metadata={
            "erasure_request_id": str(req.id),
            "maker_user_id": str(req.requesting_actor_user_id),
            "target_type": req.target_type.value,
            "target_id": str(req.target_id),
            "rejection_reason": reason,
        },
    )

    await _notify_maker_of_outcome(
        db,
        settings=settings,
        req=req,
        decider=checker,
        outcome="rejected",
        reason=reason,
    )

    log.info(
        "erasure_request_rejected",
        erasure_request_id=str(req.id),
        checker_user_id=str(checker.id),
        maker_user_id=str(req.requesting_actor_user_id),
    )
    return await _resolve_admin_response(db, req)


# --- Platform-wide ledger + audit query -------------------------------------


async def admin_list_erasure_requests(
    db: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AdminErasureRequestResponse]:
    actor = aliased(User)
    target = aliased(User)
    approver = aliased(User)
    rejecter = aliased(User)
    stmt = (
        select(
            ErasureRequest,
            actor.email.label("actor_email"),
            target.email.label("target_email"),
            approver.email.label("approver_email"),
            rejecter.email.label("rejecter_email"),
        )
        .outerjoin(actor, actor.id == ErasureRequest.requesting_actor_user_id)
        .outerjoin(target, target.id == ErasureRequest.target_user_id)
        .outerjoin(approver, approver.id == ErasureRequest.approved_by_user_id)
        .outerjoin(rejecter, rejecter.id == ErasureRequest.rejected_by_user_id)
        .order_by(desc(ErasureRequest.requested_at))
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        try:
            status_enum = DbErasureStatus(status)
        except ValueError as exc:
            raise GovernanceError(
                f"Unknown erasure status '{status}'.",
                details={"valid": [s.value for s in DbErasureStatus]},
            ) from exc
        stmt = stmt.where(ErasureRequest.status == status_enum)

    rows = (await db.execute(stmt)).all()
    out: list[AdminErasureRequestResponse] = []
    for req, actor_email, target_email, approver_email, rejecter_email in rows:
        out.append(
            AdminErasureRequestResponse(
                id=req.id,
                requesting_actor_user_id=req.requesting_actor_user_id,
                requesting_actor_email=actor_email,
                target_user_id=req.target_user_id,
                target_user_email=target_email,
                target_type=ErasureTargetType(req.target_type.value),
                target_id=req.target_id,
                jurisdiction=ErasureJurisdiction(req.jurisdiction.value),
                request_basis=ErasureBasis(req.request_basis.value),
                requested_at=req.requested_at,
                processed_at=req.processed_at,
                status=ErasureStatus(req.status.value),
                statutory_retention_applied=req.statutory_retention_applied,
                notes=req.notes,
                requires_approval=req.requires_approval,
                approved_by_user_id=req.approved_by_user_id,
                approved_by_email=approver_email,
                approved_at=req.approved_at,
                rejected_by_user_id=req.rejected_by_user_id,
                rejected_by_email=rejecter_email,
                rejected_at=req.rejected_at,
                rejection_reason=req.rejection_reason,
            )
        )
    return out


async def admin_query_audit_log(
    db: AsyncSession,
    *,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AuditLogResponse:
    actor = aliased(User)
    base = select(AuditLog)
    count_base = select(func.count(AuditLog.id))

    if action is not None:
        try:
            action_enum = AuditAction(action)
        except ValueError as exc:
            raise GovernanceError(
                f"Unknown audit action '{action}'.",
                details={"valid_actions": [a.value for a in AuditAction]},
            ) from exc
        base = base.where(AuditLog.action == action_enum)
        count_base = count_base.where(AuditLog.action == action_enum)
    if actor_id is not None:
        base = base.where(AuditLog.actor_id == actor_id)
        count_base = count_base.where(AuditLog.actor_id == actor_id)

    total = int((await db.execute(count_base)).scalar_one())

    stmt = (
        base.add_columns(actor.email.label("actor_email"))
        .outerjoin(actor, actor.id == AuditLog.actor_id)
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    entries: list[AuditLogEntry] = []
    for entry, actor_email in rows:
        entries.append(
            AuditLogEntry(
                id=entry.id,
                actor_id=entry.actor_id,
                actor_email=actor_email,
                action=entry.action.value,
                resource=entry.resource,
                ip_address=entry.ip_address,
                metadata_json=entry.metadata_json or {},
                created_at=entry.created_at,
            )
        )
    return AuditLogResponse(entries=entries, total=total, limit=limit, offset=offset)
