"""Study domain service — subjects + sessions + active-session lookup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from victus_api.audit.service import write_audit
from victus_api.core.exceptions import (
    ConflictError,
    NotFoundError,
    VictusError,
)
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    RppgCalibrationRecord,
    StudySession,
    StudySubject,
    User,
)
from victus_api.db.models import (
    FitzpatrickScale as DbFitzpatrick,
)
from victus_api.db.models import (
    Posture as DbPosture,
)
from victus_api.db.models import (
    SexAtBirth as DbSexAtBirth,
)
from victus_api.db.models import (
    TimeOfDay as DbTimeOfDay,
)
from victus_api.study import (
    CONSENT_PROTOCOL_VERSION,
    STUDY_PROTOCOL_VERSION,
)
from victus_api.study.schemas import (
    CreateSubjectRequest,
    EndSessionRequest,
    Posture,
    SexAtBirth,
    StartSessionRequest,
    StudySessionResponse,
    StudySubjectResponse,
    TimeOfDay,
)

log = get_logger(__name__)


# --- Subjects ----------------------------------------------------------------


async def create_subject(
    db: AsyncSession,
    *,
    user: User,
    payload: CreateSubjectRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> StudySubjectResponse:
    consent_version = (
        payload.consent_protocol_version or CONSENT_PROTOCOL_VERSION
    )
    row = StudySubject(
        user_id=user.id,
        external_subject_id=payload.external_subject_id,
        age_years=payload.age_years,
        sex_assigned_at_birth=DbSexAtBirth(payload.sex_assigned_at_birth.value),
        fitzpatrick_scale=(
            DbFitzpatrick(payload.fitzpatrick_scale.value)
            if payload.fitzpatrick_scale is not None
            else None
        ),
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        medical_history_summary=payload.medical_history_summary,
        consent_protocol_version=consent_version,
        is_active=True,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"You already have a subject with external id "
            f"'{payload.external_subject_id}'.",
            details={"external_subject_id": payload.external_subject_id},
        ) from exc

    await write_audit(
        db,
        action=AuditAction.STUDY_SUBJECT_CREATED,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"study:subject:{row.id}",
        metadata={
            "subject_id": str(row.id),
            "external_subject_id": payload.external_subject_id,
            "age_years": payload.age_years,
            "sex_assigned_at_birth": payload.sex_assigned_at_birth.value,
            "fitzpatrick_scale": payload.fitzpatrick_scale.value
            if payload.fitzpatrick_scale
            else None,
            "consent_protocol_version": consent_version,
        },
    )

    log.info(
        "study_subject_created",
        subject_id=str(row.id),
        external_subject_id=payload.external_subject_id,
    )
    return await _subject_to_response(db, row)


async def list_subjects(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 200,
) -> list[StudySubjectResponse]:
    stmt = (
        select(StudySubject)
        .where(StudySubject.user_id == user_id)
        .order_by(desc(StudySubject.enrolled_at))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    return [await _subject_to_response(db, r) for r in rows]


async def get_subject(
    db: AsyncSession, *, user_id: uuid.UUID, subject_id: uuid.UUID
) -> StudySubjectResponse:
    row = await db.scalar(
        select(StudySubject).where(
            StudySubject.id == subject_id,
            StudySubject.user_id == user_id,
        )
    )
    if row is None:
        raise NotFoundError("Study subject not found for this user.")
    return await _subject_to_response(db, row)


# --- Sessions ---------------------------------------------------------------


def _derive_time_of_day(now: datetime) -> TimeOfDay:
    hour = now.hour
    if 4 <= hour < 12:
        return TimeOfDay.MORNING
    if 12 <= hour < 17:
        return TimeOfDay.AFTERNOON
    if 17 <= hour < 22:
        return TimeOfDay.EVENING
    return TimeOfDay.NIGHT


async def start_session(
    db: AsyncSession,
    *,
    user: User,
    payload: StartSessionRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> StudySessionResponse:
    subject = await db.scalar(
        select(StudySubject).where(
            StudySubject.id == payload.study_subject_id,
            StudySubject.user_id == user.id,
        )
    )
    if subject is None:
        raise NotFoundError("Study subject not found for this user.")
    if not subject.is_active:
        raise VictusError(
            "Subject is inactive; reactivate before starting a session.",
            details={"subject_id": str(subject.id)},
        )

    # Auto-end any active (un-ended) session for this user so the partial-
    # unique constraint on study_sessions(user_id) WHERE ended_at IS NULL
    # never trips. This is intentional: at most one active session per
    # researcher avoids ambiguity in the calibration auto-attach logic.
    now = datetime.now(tz=UTC)
    await db.execute(
        update(StudySession)
        .where(
            StudySession.user_id == user.id,
            StudySession.ended_at.is_(None),
        )
        .values(ended_at=now)
    )

    tod = payload.time_of_day or _derive_time_of_day(now)
    row = StudySession(
        user_id=user.id,
        study_subject_id=subject.id,
        posture=DbPosture(payload.posture.value),
        time_of_day=DbTimeOfDay(tod.value),
        ambient_lux=payload.ambient_lux,
        ambient_temperature_c=payload.ambient_temperature_c,
        room_humidity_pct=payload.room_humidity_pct,
        fasted_hours=payload.fasted_hours,
        caffeine_within_2h=payload.caffeine_within_2h,
        nicotine_within_2h=payload.nicotine_within_2h,
        alcohol_within_24h=payload.alcohol_within_24h,
        last_exercise_hours_ago=payload.last_exercise_hours_ago,
        recording_site_label=payload.recording_site_label,
        protocol_version=payload.protocol_version or STUDY_PROTOCOL_VERSION,
        notes=payload.notes,
        is_locked=False,
    )
    db.add(row)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.STUDY_SESSION_STARTED,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"study:session:{row.id}",
        metadata=_session_audit_metadata(row, subject),
    )

    log.info(
        "study_session_started",
        session_id=str(row.id),
        subject_id=str(subject.id),
        posture=row.posture.value,
        time_of_day=row.time_of_day.value,
    )
    return await _session_to_response(db, row, subject=subject)


async def get_active_session(
    db: AsyncSession, *, user_id: uuid.UUID
) -> StudySessionResponse | None:
    stmt = (
        select(StudySession)
        .where(
            StudySession.user_id == user_id,
            StudySession.ended_at.is_(None),
        )
        .options(selectinload(StudySession.subject))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return await _session_to_response(db, row, subject=row.subject)


async def get_session(
    db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> StudySessionResponse:
    row = await db.scalar(
        select(StudySession)
        .where(
            StudySession.id == session_id,
            StudySession.user_id == user_id,
        )
        .options(selectinload(StudySession.subject))
    )
    if row is None:
        raise NotFoundError("Study session not found for this user.")
    return await _session_to_response(db, row, subject=row.subject)


async def list_sessions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 50,
) -> list[StudySessionResponse]:
    stmt = (
        select(StudySession)
        .where(StudySession.user_id == user_id)
        .order_by(desc(StudySession.session_started_at))
        .options(selectinload(StudySession.subject))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    return [await _session_to_response(db, r, subject=r.subject) for r in rows]


async def end_session(
    db: AsyncSession,
    *,
    user: User,
    session_id: uuid.UUID,
    payload: EndSessionRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> StudySessionResponse:
    row = await db.scalar(
        select(StudySession)
        .where(
            StudySession.id == session_id,
            StudySession.user_id == user.id,
        )
        .options(selectinload(StudySession.subject))
    )
    if row is None:
        raise NotFoundError("Study session not found for this user.")
    if row.ended_at is not None:
        # Idempotent — return current state without flipping fields again.
        return await _session_to_response(db, row, subject=row.subject)
    row.ended_at = datetime.now(tz=UTC)
    if payload.notes:
        row.notes = (
            f"{row.notes}\n\n[end] {payload.notes}"
            if row.notes
            else payload.notes
        )
    await db.flush()
    await write_audit(
        db,
        action=AuditAction.STUDY_SESSION_ENDED,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"study:session:{row.id}",
        metadata=_session_audit_metadata(row, row.subject),
    )
    return await _session_to_response(db, row, subject=row.subject)


async def lock_session_if_needed(
    db: AsyncSession,
    *,
    session: StudySession,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Idempotent: locks the session on its first associated capture."""
    if session.is_locked:
        return
    session.is_locked = True
    session.locked_at = datetime.now(tz=UTC)
    await db.flush()
    await write_audit(
        db,
        action=AuditAction.STUDY_SESSION_LOCKED,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"study:session:{session.id}",
        metadata={
            "session_id": str(session.id),
            "subject_id": str(session.study_subject_id),
            "locked_at": session.locked_at.isoformat() if session.locked_at else None,
        },
    )


# --- Helpers ----------------------------------------------------------------


async def _subject_to_response(
    db: AsyncSession, row: StudySubject
) -> StudySubjectResponse:
    session_count = int(
        (
            await db.execute(
                select(func.count(StudySession.id)).where(
                    StudySession.study_subject_id == row.id
                )
            )
        ).scalar_one()
    )
    pair_count = int(
        (
            await db.execute(
                select(func.count(RppgCalibrationRecord.id))
                .join(
                    StudySession,
                    StudySession.id == RppgCalibrationRecord.study_session_id,
                )
                .where(StudySession.study_subject_id == row.id)
            )
        ).scalar_one()
    )
    return StudySubjectResponse(
        id=row.id,
        external_subject_id=row.external_subject_id,
        age_years=row.age_years,
        sex_assigned_at_birth=SexAtBirth(row.sex_assigned_at_birth.value),
        fitzpatrick_scale=(
            None
            if row.fitzpatrick_scale is None
            else __import__(
                "victus_api.toi.schemas", fromlist=["FitzpatrickScale"]
            ).FitzpatrickScale(row.fitzpatrick_scale.value)
        ),
        height_cm=row.height_cm,
        weight_kg=row.weight_kg,
        medical_history_summary=row.medical_history_summary,
        consent_protocol_version=row.consent_protocol_version,
        enrolled_at=row.enrolled_at,
        is_active=row.is_active,
        session_count=session_count,
        pair_count=pair_count,
    )


async def _session_to_response(
    db: AsyncSession,
    row: StudySession,
    *,
    subject: StudySubject,
) -> StudySessionResponse:
    pair_count = int(
        (
            await db.execute(
                select(func.count(RppgCalibrationRecord.id)).where(
                    RppgCalibrationRecord.study_session_id == row.id
                )
            )
        ).scalar_one()
    )
    return StudySessionResponse(
        id=row.id,
        study_subject_id=subject.id,
        external_subject_id=subject.external_subject_id,
        session_started_at=row.session_started_at,
        posture=Posture(row.posture.value),
        time_of_day=TimeOfDay(row.time_of_day.value),
        ambient_lux=row.ambient_lux,
        ambient_temperature_c=row.ambient_temperature_c,
        room_humidity_pct=row.room_humidity_pct,
        fasted_hours=row.fasted_hours,
        caffeine_within_2h=row.caffeine_within_2h,
        nicotine_within_2h=row.nicotine_within_2h,
        alcohol_within_24h=row.alcohol_within_24h,
        last_exercise_hours_ago=row.last_exercise_hours_ago,
        recording_site_label=row.recording_site_label,
        protocol_version=row.protocol_version,
        notes=row.notes,
        is_locked=row.is_locked,
        locked_at=row.locked_at,
        ended_at=row.ended_at,
        pair_count=pair_count,
    )


def _session_audit_metadata(
    session: StudySession, subject: StudySubject
) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "subject_id": str(subject.id),
        "external_subject_id": subject.external_subject_id,
        "posture": session.posture.value,
        "time_of_day": session.time_of_day.value,
        "protocol_version": session.protocol_version,
        "is_locked": session.is_locked,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }
