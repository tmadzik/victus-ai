"""Governance domain service — erasure, anonymisation, subject access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.config import Settings
from victus_api.core.exceptions import (
    NotFoundError,
    VictusError,
)
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    ConsentRecord,
    ErasureRequest,
    RefreshToken,
    RppgCalibrationRecord,
    StudySession,
    StudySubject,
    ToiAssessment,
    TriageAssessment,
    User,
)
from victus_api.db.models import (
    ErasureBasis as DbErasureBasis,
)
from victus_api.db.models import (
    ErasureJurisdiction as DbErasureJurisdiction,
)
from victus_api.db.models import (
    ErasureStatus as DbErasureStatus,
)
from victus_api.db.models import (
    ErasureTargetType as DbErasureTargetType,
)
from victus_api.governance.anonymiser import (
    pseudonymise_subject_id,
    tombstone_email,
    tombstone_name,
)
from victus_api.governance.schemas import (
    AnonymiseSubjectRequest,
    DataInventoryCounts,
    EraseAccountRequest,
    ErasureBasis,
    ErasureJurisdiction,
    ErasureRequestResponse,
    ErasureStatus,
    ErasureTargetType,
    MyDataSummary,
)
from victus_api.notifications.schemas import NotificationType
from victus_api.notifications.service import fan_out_to_admins
from victus_api.worker.jobs import scrub_user

log = get_logger(__name__)

# Deep link the in-app + webhook notifications point at.
PENDING_QUEUE_PATH = "/admin/governance?tab=pending"


async def _notify_checkers_of_pending(
    db: AsyncSession,
    *,
    settings: Settings,
    request_row: ErasureRequest,
    maker: User,
    target_label: str,
    target_kind: str,
) -> None:
    """Fan a notification out to every eligible checker (all active admins
    except the maker, who cannot approve their own request).
    """
    maker_label = maker.email or str(maker.id)
    title = "Erasure approval needed"
    body = (
        f"{maker_label} proposed erasing a {target_kind} "
        f"(`{target_label}`). A second administrator must approve before any "
        f"data is destroyed."
    )
    await fan_out_to_admins(
        db,
        settings=settings,
        type_=NotificationType.ERASURE_APPROVAL_REQUESTED,
        title=title,
        body=body,
        resource_path=PENDING_QUEUE_PATH,
        payload={
            "erasure_request_id": str(request_row.id),
            "target_type": request_row.target_type.value,
            "maker_user_id": str(maker.id),
        },
        exclude_user_id=maker.id,
        webhook_fields={
            "Target": target_label,
            "Maker": maker_label,
            "Basis": request_row.request_basis.value,
            "Jurisdiction": request_row.jurisdiction.value,
        },
    )


RETENTION_POLICY_SUMMARY = (
    "On erasure, your PII (email, name, password) is tombstoned and your "
    "study subjects are anonymised via salted SHA-256. De-identified "
    "biometric records (triage assessments, TOI assessments, calibration "
    "pairs) are retained for research integrity under GDPR Article "
    "17(3)(d) / POPIA section 14(3) since they no longer identify you. "
    "Audit-log rows referencing your historical user_id are preserved as "
    "regulatory evidence that the erasure was honoured."
)


class GovernanceError(VictusError):
    status_code = 400
    error_code = "governance_error"


# --- Account erasure (self-service) -----------------------------------------


async def _create_account_erasure_request(
    db: AsyncSession,
    *,
    actor_user: User,
    target_user: User,
    jurisdiction: ErasureJurisdiction,
    request_basis: ErasureBasis,
    notes: str | None,
    requires_approval: bool,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> ErasureRequest:
    """Maker step — record the intent to erase an account.

    Leaves the target's data completely intact. ``requires_approval=True``
    parks the request in ``AWAITING_APPROVAL`` for a second admin (checker)
    and fans a notification out to every eligible checker; ``False`` parks it
    in ``PENDING`` for immediate execution by the caller (self-service).
    """
    if target_user.erased_at is not None:
        raise GovernanceError(
            "This account has already been erased.",
            details={"erased_at": target_user.erased_at.isoformat()},
        )

    initial_status = (
        ErasureStatus.AWAITING_APPROVAL if requires_approval else ErasureStatus.PENDING
    )
    is_admin = actor_user.id != target_user.id

    request_row = ErasureRequest(
        requesting_actor_user_id=actor_user.id,
        target_user_id=target_user.id,
        target_type=DbErasureTargetType(ErasureTargetType.USER_ACCOUNT.value),
        target_id=target_user.id,
        jurisdiction=DbErasureJurisdiction(jurisdiction.value),
        request_basis=DbErasureBasis(request_basis.value),
        status=DbErasureStatus(initial_status.value),
        statutory_retention_applied=True,
        retention_basis=RETENTION_POLICY_SUMMARY,
        notes=notes,
        requires_approval=requires_approval,
    )
    db.add(request_row)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.ACCOUNT_ERASURE_REQUESTED,
        actor_id=actor_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:erasure:{request_row.id}",
        metadata={
            "erasure_request_id": str(request_row.id),
            "target_user_id": str(target_user.id),
            "jurisdiction": jurisdiction.value,
            "request_basis": request_basis.value,
            "actor_kind": "admin" if is_admin else "self",
            "requires_approval": requires_approval,
        },
    )

    if requires_approval:
        await _notify_checkers_of_pending(
            db,
            settings=settings,
            request_row=request_row,
            maker=actor_user,
            target_label=target_user.email or str(target_user.id),
            target_kind="user account",
        )

    log.info(
        "account_erasure_requested",
        actor_user_id=str(actor_user.id),
        target_user_id=str(target_user.id),
        erasure_request_id=str(request_row.id),
        requires_approval=requires_approval,
        actor_kind="admin" if is_admin else "self",
    )
    return request_row


async def _execute_account_erasure(
    db: AsyncSession,
    *,
    request_row: ErasureRequest,
    executor_user: User,
    target_user: User,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Checker / self-service step — perform the actual tombstoning.

    Re-checks ``erased_at`` because time may have passed between the maker
    request and the checker approval (e.g. the subject self-erased in the
    interim).
    """
    if target_user.erased_at is not None:
        raise GovernanceError(
            "This account has already been erased.",
            details={"erased_at": target_user.erased_at.isoformat()},
        )

    now = datetime.now(tz=UTC)
    salt = settings.pseudo_salt.get_secret_value()

    subject_rows = (
        await db.scalars(
            select(StudySubject).where(
                StudySubject.user_id == target_user.id,
                StudySubject.anonymised_at.is_(None),
            )
        )
    ).all()
    for subject in subject_rows:
        _apply_subject_anonymisation(
            subject,
            salt=salt,
            erasure_request_id=request_row.id,
            now=now,
        )

    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == target_user.id)
    )

    # Bring the WhatsApp rail under erasure: scrub PII from any processing jobs
    # linked to this account (phone, media, intake, derived vitals).
    jobs_scrubbed = await scrub_user(db, target_user.id)

    target_user.email = tombstone_email(target_user.id)
    target_user.full_name = tombstone_name()
    target_user.hashed_password = None
    target_user.is_active = False
    target_user.erased_at = now
    target_user.erasure_request_id = request_row.id

    request_row.processed_at = now
    request_row.status = DbErasureStatus(ErasureStatus.COMPLETED.value)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.ACCOUNT_ERASED,
        actor_id=executor_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:erasure:{request_row.id}",
        metadata={
            "erasure_request_id": str(request_row.id),
            "target_user_id": str(target_user.id),
            "subjects_anonymised": len(subject_rows),
            "whatsapp_jobs_scrubbed": jobs_scrubbed,
            "retention_basis": "GDPR_17_3_d_POPIA_14_3_research",
        },
    )

    log.info(
        "account_erased",
        executor_user_id=str(executor_user.id),
        target_user_id=str(target_user.id),
        erasure_request_id=str(request_row.id),
        subjects_anonymised=len(subject_rows),
    )


async def _apply_account_erasure(
    db: AsyncSession,
    *,
    actor_user: User,
    target_user: User,
    jurisdiction: ErasureJurisdiction,
    request_basis: ErasureBasis,
    notes: str | None,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> ErasureRequestResponse:
    """One-shot erasure (self-service): create + execute atomically."""
    request_row = await _create_account_erasure_request(
        db,
        actor_user=actor_user,
        target_user=target_user,
        jurisdiction=jurisdiction,
        request_basis=request_basis,
        notes=notes,
        requires_approval=False,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await _execute_account_erasure(
        db,
        request_row=request_row,
        executor_user=actor_user,
        target_user=target_user,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return _request_to_response(request_row)


async def erase_account_self_service(
    db: AsyncSession,
    *,
    user: User,
    payload: EraseAccountRequest,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> ErasureRequestResponse:
    if user.email is None or user.email.lower() != payload.confirm_email.lower():
        raise GovernanceError(
            "Confirm-email does not match the account email; erasure not performed.",
        )
    return await _apply_account_erasure(
        db,
        actor_user=user,
        target_user=user,
        jurisdiction=payload.jurisdiction,
        request_basis=payload.request_basis,
        notes=payload.notes,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )


# --- Subject anonymisation --------------------------------------------------


async def _create_subject_anonymisation_request(
    db: AsyncSession,
    *,
    actor_user: User,
    subject: StudySubject,
    jurisdiction: ErasureJurisdiction,
    request_basis: ErasureBasis,
    notes: str | None,
    requires_approval: bool,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> ErasureRequest:
    """Maker step — record the intent to anonymise a subject. Data untouched."""
    if subject.anonymised_at is not None:
        raise GovernanceError(
            "This subject has already been anonymised.",
            details={"anonymised_at": subject.anonymised_at.isoformat()},
        )

    salt = settings.pseudo_salt.get_secret_value()
    is_admin = actor_user.id != subject.user_id
    initial_status = (
        ErasureStatus.AWAITING_APPROVAL if requires_approval else ErasureStatus.PENDING
    )

    request_row = ErasureRequest(
        requesting_actor_user_id=actor_user.id,
        target_user_id=subject.user_id,
        target_type=DbErasureTargetType(ErasureTargetType.STUDY_SUBJECT.value),
        target_id=subject.id,
        jurisdiction=DbErasureJurisdiction(jurisdiction.value),
        request_basis=DbErasureBasis(request_basis.value),
        status=DbErasureStatus(initial_status.value),
        statutory_retention_applied=True,
        retention_basis=RETENTION_POLICY_SUMMARY,
        notes=notes,
        requires_approval=requires_approval,
    )
    db.add(request_row)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.SUBJECT_ANONYMISATION_REQUESTED,
        actor_id=actor_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:erasure:{request_row.id}",
        metadata={
            "erasure_request_id": str(request_row.id),
            "subject_id": str(subject.id),
            "owning_user_id": str(subject.user_id),
            "original_external_subject_id_hash": _short_hash(
                f"{subject.external_subject_id}:{salt}"
            ),
            "jurisdiction": jurisdiction.value,
            "request_basis": request_basis.value,
            "actor_kind": "admin" if is_admin else "self",
            "requires_approval": requires_approval,
        },
    )

    if requires_approval:
        await _notify_checkers_of_pending(
            db,
            settings=settings,
            request_row=request_row,
            maker=actor_user,
            target_label=subject.external_subject_id,
            target_kind="study subject",
        )

    log.info(
        "subject_anonymisation_requested",
        subject_id=str(subject.id),
        actor_user_id=str(actor_user.id),
        erasure_request_id=str(request_row.id),
        requires_approval=requires_approval,
    )
    return request_row


async def _execute_subject_anonymisation(
    db: AsyncSession,
    *,
    request_row: ErasureRequest,
    executor_user: User,
    subject: StudySubject,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Checker / self-service step — perform the actual anonymisation."""
    if subject.anonymised_at is not None:
        raise GovernanceError(
            "This subject has already been anonymised.",
            details={"anonymised_at": subject.anonymised_at.isoformat()},
        )
    now = datetime.now(tz=UTC)
    salt = settings.pseudo_salt.get_secret_value()

    _apply_subject_anonymisation(
        subject,
        salt=salt,
        erasure_request_id=request_row.id,
        now=now,
    )

    request_row.processed_at = now
    request_row.status = DbErasureStatus(ErasureStatus.COMPLETED.value)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.SUBJECT_ANONYMISED,
        actor_id=executor_user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:erasure:{request_row.id}",
        metadata={
            "erasure_request_id": str(request_row.id),
            "subject_id": str(subject.id),
            "owning_user_id": str(subject.user_id),
            "pseudonym": subject.external_subject_id,
        },
    )
    log.info(
        "subject_anonymised",
        subject_id=str(subject.id),
        executor_user_id=str(executor_user.id),
        pseudonym=subject.external_subject_id,
        erasure_request_id=str(request_row.id),
    )


async def anonymise_subject_record(
    db: AsyncSession,
    *,
    actor_user: User,
    subject: StudySubject,
    jurisdiction: ErasureJurisdiction,
    request_basis: ErasureBasis,
    notes: str | None,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> ErasureRequestResponse:
    """One-shot anonymisation (self-service): create + execute atomically."""
    request_row = await _create_subject_anonymisation_request(
        db,
        actor_user=actor_user,
        subject=subject,
        jurisdiction=jurisdiction,
        request_basis=request_basis,
        notes=notes,
        requires_approval=False,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await _execute_subject_anonymisation(
        db,
        request_row=request_row,
        executor_user=actor_user,
        subject=subject,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return _request_to_response(request_row)


async def anonymise_subject(
    db: AsyncSession,
    *,
    user: User,
    subject_id: uuid.UUID,
    payload: AnonymiseSubjectRequest,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> ErasureRequestResponse:
    subject = await db.scalar(
        select(StudySubject).where(
            StudySubject.id == subject_id,
            StudySubject.user_id == user.id,
        )
    )
    if subject is None:
        raise NotFoundError("Study subject not found for this researcher.")
    return await anonymise_subject_record(
        db,
        actor_user=user,
        subject=subject,
        jurisdiction=payload.jurisdiction,
        request_basis=payload.request_basis,
        notes=payload.notes,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def _apply_subject_anonymisation(
    subject: StudySubject,
    *,
    salt: str,
    erasure_request_id: uuid.UUID,
    now: datetime,
) -> None:
    """In-place pseudonymisation of a single StudySubject row."""
    subject.external_subject_id = pseudonymise_subject_id(subject.id, salt=salt)
    subject.medical_history_summary = None
    subject.height_cm = None
    subject.weight_kg = None
    subject.is_active = False
    subject.anonymised_at = now
    subject.erasure_request_id = erasure_request_id


# --- Subject access (GDPR Art 15) -------------------------------------------


async def my_data_summary(
    db: AsyncSession,
    *,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> MyDataSummary:
    counts = await _count_data(db, user_id=user.id)

    await write_audit(
        db,
        action=AuditAction.DATA_ACCESS_REQUEST_FULFILLED,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"governance:data-summary:{user.id}",
        metadata=counts.model_dump(),
    )

    return MyDataSummary(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        erased_at=user.erased_at,
        counts=counts,
        retention_policy_summary=RETENTION_POLICY_SUMMARY,
    )


async def list_my_erasure_requests(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 50,
) -> list[ErasureRequestResponse]:
    stmt = (
        select(ErasureRequest)
        .where(ErasureRequest.target_user_id == user_id)
        .order_by(desc(ErasureRequest.requested_at))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    return [_request_to_response(r) for r in rows]


# --- Helpers ---------------------------------------------------------------


async def _count_data(
    db: AsyncSession, *, user_id: uuid.UUID
) -> DataInventoryCounts:
    async def _count(model: type) -> int:
        result = await db.execute(
            select(func.count(model.id)).where(model.user_id == user_id)  # type: ignore[attr-defined]
        )
        return int(result.scalar_one())

    return DataInventoryCounts(
        triage_assessments=await _count(TriageAssessment),
        toi_assessments=await _count(ToiAssessment),
        calibration_records=await _count(RppgCalibrationRecord),
        study_subjects=await _count(StudySubject),
        study_sessions=await _count(StudySession),
        consent_records=await _count(ConsentRecord),
        erasure_requests=int(
            (
                await db.execute(
                    select(func.count(ErasureRequest.id)).where(
                        ErasureRequest.target_user_id == user_id
                    )
                )
            ).scalar_one()
        ),
    )


def _short_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _request_to_response(row: ErasureRequest) -> ErasureRequestResponse:
    return ErasureRequestResponse(
        id=row.id,
        target_type=ErasureTargetType(row.target_type.value),
        target_id=row.target_id,
        jurisdiction=ErasureJurisdiction(row.jurisdiction.value),
        request_basis=ErasureBasis(row.request_basis.value),
        requested_at=row.requested_at,
        processed_at=row.processed_at,
        status=ErasureStatus(row.status.value),
        statutory_retention_applied=row.statutory_retention_applied,
        retention_basis=row.retention_basis,
        notes=row.notes,
    )
