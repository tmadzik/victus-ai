"""Referral orchestration: create + status lifecycle, both audited."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.config import Settings
from victus_api.core.exceptions import NotFoundError
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    ConsentRecord,
    ConsentType,
    NotificationType,
    Referral,
    ReferralOutcome,
    ReferralStatus,
    ResearchTriageCase,
    TriageAssessment,
    User,
)
from victus_api.notifications.service import notify_user
from victus_api.referrals.schemas import (
    CreateReferralRequest,
    RecordReferralOutcomeRequest,
    ReferralResponse,
    UpdateReferralStatusRequest,
)
from victus_api.research.schemas import CaptureDomain, ResearchCaseCreate
from victus_api.research.service import create_research_case
from victus_api.triage.schemas import Sex

log = get_logger(__name__)

# Outcomes where the participant actually attended the facility — a confirmed
# clinical value at these is meaningful ground truth.
_ATTENDED_OUTCOMES: frozenset[ReferralOutcome] = frozenset(
    {
        ReferralOutcome.ATTENDED_CONFIRMED,
        ReferralOutcome.ATTENDED_NOT_CONFIRMED,
        ReferralOutcome.ATTENDED_INCONCLUSIVE,
        ReferralOutcome.TREATMENT_STARTED,
    }
)

_REFERRALS_PATH = "/referrals"


def _to_response(row: Referral) -> ReferralResponse:
    return ReferralResponse(
        id=row.id,
        participant_user_id=row.participant_user_id,
        created_by_user_id=row.created_by_user_id,
        source_triage_assessment_id=row.source_triage_assessment_id,
        destination_type=row.destination_type.value,
        destination_name=row.destination_name,
        reason=row.reason,
        urgency=row.urgency.value,
        status=row.status.value,
        notes=row.notes,
        outcome=row.outcome.value,
        outcome_recorded_at=row.outcome_recorded_at,
        outcome_notes=row.outcome_notes,
        outcome_hba1c_percent=row.outcome_hba1c_percent,
        outcome_fasting_glucose_mmol_l=row.outcome_fasting_glucose_mmol_l,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_referral(
    db: AsyncSession,
    *,
    actor: User,
    settings: Settings,
    payload: CreateReferralRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> ReferralResponse:
    participant = await db.get(User, payload.participant_user_id)
    if participant is None:
        raise NotFoundError("Participant not found.")

    row = Referral(
        participant_user_id=payload.participant_user_id,
        created_by_user_id=actor.id,
        source_triage_assessment_id=payload.source_triage_assessment_id,
        destination_type=payload.destination_type,
        destination_name=payload.destination_name,
        reason=payload.reason,
        urgency=payload.urgency,
        status=ReferralStatus.PENDING,
        notes=payload.notes,
    )
    db.add(row)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.REFERRAL_CREATED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"referral:{row.id}",
        metadata={
            "participant_id": str(payload.participant_user_id),
            "urgency": payload.urgency.value,
            "destination_type": payload.destination_type.value,
        },
    )

    # Tell the participant they've been referred (in-app + best-effort webhook).
    urgency_label = payload.urgency.value.capitalize()
    await notify_user(
        db,
        settings=settings,
        recipient_user_id=payload.participant_user_id,
        type_=NotificationType.REFERRAL_RAISED,
        title="You have a new referral",
        body=(
            f"Your care team referred you to {payload.destination_name} "
            f"({urgency_label.lower()}). Reason: {payload.reason}"
        ),
        resource_path=_REFERRALS_PATH,
        payload={
            "referral_id": str(row.id),
            "urgency": payload.urgency.value,
            "destination_name": payload.destination_name,
        },
        webhook_fields={
            "Urgency": urgency_label,
            "Destination": payload.destination_name,
        },
    )
    return _to_response(row)


async def list_my_referrals(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 25
) -> list[ReferralResponse]:
    rows = await _list(db, participant_id=user_id, limit=limit)
    return [_to_response(r) for r in rows]


async def list_referrals_for_participant(
    db: AsyncSession, *, user_id: uuid.UUID, limit: int = 50
) -> list[ReferralResponse]:
    rows = await _list(db, participant_id=user_id, limit=limit)
    return [_to_response(r) for r in rows]


async def _list(
    db: AsyncSession, *, participant_id: uuid.UUID, limit: int
) -> list[Referral]:
    stmt = (
        select(Referral)
        .where(Referral.participant_user_id == participant_id)
        .order_by(desc(Referral.created_at))
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


async def update_referral_status(
    db: AsyncSession,
    *,
    actor: User,
    referral_id: uuid.UUID,
    payload: UpdateReferralStatusRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> ReferralResponse:
    row = await db.get(Referral, referral_id)
    if row is None:
        raise NotFoundError("Referral not found.")

    previous = row.status
    row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    await db.flush()
    # ``updated_at`` is server-generated via onupdate; reload it (and the row)
    # so the response carries the new timestamp without a lazy load.
    await db.refresh(row)

    await write_audit(
        db,
        action=AuditAction.REFERRAL_STATUS_UPDATED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"referral:{row.id}",
        metadata={
            "participant_id": str(row.participant_user_id),
            "from": previous.value,
            "to": payload.status.value,
        },
    )
    return _to_response(row)


async def record_referral_outcome(
    db: AsyncSession,
    *,
    actor: User,
    referral_id: uuid.UUID,
    payload: RecordReferralOutcomeRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> ReferralResponse:
    """Close the care loop: record the facility-confirmed clinical outcome of an
    onward referral. Audited; the outcome is orthogonal to the administrative
    ``status`` lifecycle."""
    row = await db.get(Referral, referral_id)
    if row is None:
        raise NotFoundError("Referral not found.")

    previous = row.outcome
    row.outcome = payload.outcome
    row.outcome_recorded_at = datetime.now(UTC)
    if payload.notes is not None:
        row.outcome_notes = payload.notes
    if payload.confirmed_hba1c_percent is not None:
        row.outcome_hba1c_percent = payload.confirmed_hba1c_percent
    if payload.confirmed_fasting_glucose_mmol_l is not None:
        row.outcome_fasting_glucose_mmol_l = payload.confirmed_fasting_glucose_mmol_l
    await db.flush()
    await db.refresh(row)

    # Care-loop flywheel: a confirmed outcome with facility glycaemia can seed a
    # labelled training row. Best-effort and consent-gated — it never blocks the
    # outcome from being recorded.
    research_case_id = await _maybe_seed_research_case(db, referral=row, actor=actor)

    await write_audit(
        db,
        action=AuditAction.REFERRAL_OUTCOME_RECORDED,
        actor_id=actor.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"referral:{row.id}",
        metadata={
            "participant_id": str(row.participant_user_id),
            "from": previous.value,
            "to": payload.outcome.value,
            "research_case_id": (
                str(research_case_id) if research_case_id is not None else None
            ),
        },
    )
    return _to_response(row)


async def _has_research_consent(db: AsyncSession, user_id: uuid.UUID) -> bool:
    found = await db.scalar(
        select(ConsentRecord.id)
        .where(ConsentRecord.user_id == user_id)
        .where(ConsentRecord.consent_type == ConsentType.DATA_SHARING_RESEARCH)
        .where(ConsentRecord.revoked_at.is_(None))
        .limit(1)
    )
    return found is not None


async def _maybe_seed_research_case(
    db: AsyncSession, *, referral: Referral, actor: User
) -> uuid.UUID | None:
    """Seed a labelled research case from a confirmed referral outcome.

    All of the following must hold, else this is a no-op (the outcome still
    records): the participant attended the facility; the referral links to a
    source Pathway A assessment; facility glycaemia (HbA1c/FPG — the diabetes
    ground truth) was supplied; the participant consented to research data use;
    the source assessment has a BP reading (needed for the hypertension label);
    and no case has already been seeded from that assessment.
    """
    if referral.outcome not in _ATTENDED_OUTCOMES:
        return None
    if referral.source_triage_assessment_id is None:
        return None
    if (
        referral.outcome_hba1c_percent is None
        and referral.outcome_fasting_glucose_mmol_l is None
    ):
        return None
    if not await _has_research_consent(db, referral.participant_user_id):
        return None
    already = await db.scalar(
        select(ResearchTriageCase.id)
        .where(
            ResearchTriageCase.source_triage_assessment_id
            == referral.source_triage_assessment_id
        )
        .limit(1)
    )
    if already is not None:
        return None
    assessment = await db.get(TriageAssessment, referral.source_triage_assessment_id)
    if assessment is None:
        return None
    raw = assessment.raw_inputs or {}
    if raw.get("systolic_bp_mmhg") is None or raw.get("diastolic_bp_mmhg") is None:
        return None

    participant = await db.get(User, referral.participant_user_id)
    site = participant.site_code if participant is not None else None
    try:
        payload = ResearchCaseCreate(
            age_years=raw["age_years"],
            sex=Sex(raw["sex"]),
            height_cm=raw["height_cm"],
            weight_kg=raw["weight_kg"],
            waist_cm=raw["waist_cm"],
            hip_cm=raw.get("hip_cm"),
            systolic_bp_mmhg=raw.get("systolic_bp_mmhg"),
            diastolic_bp_mmhg=raw.get("diastolic_bp_mmhg"),
            hba1c_percent=referral.outcome_hba1c_percent,
            fasting_glucose_mmol_l=referral.outcome_fasting_glucose_mmol_l,
            capture_domain=CaptureDomain.CLINICAL_GRADE,
            notes=(
                f"Seeded from referral {referral.id} "
                f"({referral.outcome.value}) via the care-loop flywheel."
            ),
        )
        case = await create_research_case(
            db,
            payload=payload,
            created_by=actor,
            site_code=site,
            source_triage_assessment_id=referral.source_triage_assessment_id,
        )
    except Exception:
        log.warning(
            "outcome_research_seed_failed",
            referral_id=str(referral.id),
            exc_info=True,
        )
        return None
    log.info(
        "outcome_seeded_research_case",
        referral_id=str(referral.id),
        research_case_id=str(case.id),
    )
    return case.id
