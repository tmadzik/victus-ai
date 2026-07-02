"""Enrollment service: capture the participant profile + consent, gate access.

The external patient id is hashed (never stored plain); the region is mapped to
the governing data-protection jurisdiction; consent to both pathways is recorded
as ``consent_records`` and is what the enrollment gate checks. Every enrollment
is audited (``CONSENT_GRANTED`` with ``mode: "enrollment"``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.config import Settings
from victus_api.db.models import (
    AuditAction,
    ConsentRecord,
    ConsentType,
    ErasureJurisdiction,
    ParticipantProfile,
    User,
)
from victus_api.enrollment.schemas import (
    EnrollmentRequest,
    EnrollmentStatusResponse,
    ProfileResponse,
)
from victus_api.enrollment.security import CONSENT_VERSION, hash_patient_id
from victus_api.governance.jurisdictions import jurisdiction_for_site

# Both pathways must be consented before a participant is cleared for the app.
REQUIRED_CONSENTS: tuple[ConsentType, ...] = (
    ConsentType.TRIAGE,
    ConsentType.TOI_IMAGING,
)


async def _active_consent_types(db: AsyncSession, user_id) -> set[ConsentType]:  # noqa: ANN001
    rows = (
        await db.execute(
            select(ConsentRecord.consent_type).where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    return set(rows)


async def _ensure_consent(
    db: AsyncSession, user_id, consent_type: ConsentType, active: set[ConsentType]  # noqa: ANN001
) -> None:
    """Idempotently record an active consent (no duplicate rows)."""
    if consent_type in active:
        return
    db.add(
        ConsentRecord(
            user_id=user_id, consent_type=consent_type, version=CONSENT_VERSION
        )
    )
    active.add(consent_type)


async def get_enrollment_status(
    db: AsyncSession, *, user: User
) -> EnrollmentStatusResponse:
    profile = (
        await db.execute(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    active = await _active_consent_types(db, user.id)
    missing = [c.value for c in REQUIRED_CONSENTS if c not in active]
    return EnrollmentStatusResponse(
        enrolled=profile is not None and not missing,
        has_profile=profile is not None,
        missing_consents=missing,
    )


def _profile_response(profile: ParticipantProfile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        user_id=profile.user_id,
        full_name=profile.full_name,
        email=profile.email,
        patient_id_hash=profile.patient_id_hash,
        age_range=profile.age_range,
        biological_sex=profile.biological_sex.value,
        region=profile.region,
        race_ethnicity=profile.race_ethnicity,
        jurisdiction=profile.jurisdiction,
        enrolled_at=profile.enrolled_at,
    )


async def enroll(
    db: AsyncSession,
    *,
    user: User,
    payload: EnrollmentRequest,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> ProfileResponse:
    """Create/update the participant profile + record consent. Idempotent."""
    jurisdiction = jurisdiction_for_site(
        payload.region.value, fallback=ErasureJurisdiction.OTHER
    ).value
    patient_hash = hash_patient_id(
        payload.patient_id, salt=settings.pseudo_salt.get_secret_value()
    )

    profile = (
        await db.execute(
            select(ParticipantProfile).where(ParticipantProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = ParticipantProfile(user_id=user.id, enrolled_at=datetime.now(UTC))
        db.add(profile)
    profile.full_name = payload.full_name
    profile.email = str(payload.email)
    profile.patient_id_hash = patient_hash
    profile.age_range = payload.age_range.value
    profile.biological_sex = payload.biological_sex
    profile.region = payload.region.value
    profile.race_ethnicity = payload.race_ethnicity
    profile.jurisdiction = jurisdiction

    # Keep the participant's site aligned so downstream records (kiosk/WhatsApp,
    # research) inherit the same jurisdiction.
    if payload.region is not payload.region.OTHER:
        user.site_code = payload.region.value

    active = await _active_consent_types(db, user.id)
    await _ensure_consent(db, user.id, ConsentType.TRIAGE, active)
    await _ensure_consent(db, user.id, ConsentType.TOI_IMAGING, active)
    if payload.consent_research:
        await _ensure_consent(db, user.id, ConsentType.DATA_SHARING_RESEARCH, active)

    await db.flush()
    await write_audit(
        db,
        action=AuditAction.CONSENT_GRANTED,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"enrollment:{profile.id}",
        metadata={
            "mode": "enrollment",
            "jurisdiction": jurisdiction,
            "consents": sorted(active_c.value for active_c in active),
        },
    )
    return _profile_response(profile)
