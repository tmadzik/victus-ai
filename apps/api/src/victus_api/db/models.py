"""ORM models — kept in lockstep with the Alembic migration history."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from victus_api.db.base import Base


class UserRole(str, enum.Enum):
    PATIENT = "PATIENT"
    CHW = "CHW"
    CLINICIAN = "CLINICIAN"
    ADMIN = "ADMIN"


class ConsentType(str, enum.Enum):
    TRIAGE = "TRIAGE"
    TOI_IMAGING = "TOI_IMAGING"
    DATA_SHARING_RESEARCH = "DATA_SHARING_RESEARCH"


class AuditAction(str, enum.Enum):
    AUTH_REGISTER = "AUTH_REGISTER"
    AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILURE = "AUTH_LOGIN_FAILURE"
    AUTH_REFRESH = "AUTH_REFRESH"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    PATHWAY_A_ENTERED = "PATHWAY_A_ENTERED"
    PATHWAY_B_ENTERED = "PATHWAY_B_ENTERED"
    PATHWAY_A_RESULT_GREEN = "PATHWAY_A_RESULT_GREEN"
    PATHWAY_A_RESULT_YELLOW = "PATHWAY_A_RESULT_YELLOW"
    PATHWAY_A_RESULT_RED = "PATHWAY_A_RESULT_RED"
    PATHWAY_A_SAFETY_OVERRIDE = "PATHWAY_A_SAFETY_OVERRIDE"
    PATHWAY_B_ASSESSMENT_COMPLETED = "PATHWAY_B_ASSESSMENT_COMPLETED"
    PATHWAY_B_QUALITY_REJECTED = "PATHWAY_B_QUALITY_REJECTED"
    CALIBRATION_PAIR_RECORDED = "CALIBRATION_PAIR_RECORDED"
    STUDY_SUBJECT_CREATED = "STUDY_SUBJECT_CREATED"
    STUDY_SESSION_STARTED = "STUDY_SESSION_STARTED"
    STUDY_SESSION_LOCKED = "STUDY_SESSION_LOCKED"
    STUDY_SESSION_ENDED = "STUDY_SESSION_ENDED"
    ACCOUNT_ERASURE_REQUESTED = "ACCOUNT_ERASURE_REQUESTED"
    ACCOUNT_ERASED = "ACCOUNT_ERASED"
    SUBJECT_ANONYMISATION_REQUESTED = "SUBJECT_ANONYMISATION_REQUESTED"
    SUBJECT_ANONYMISED = "SUBJECT_ANONYMISED"
    DATA_ACCESS_REQUEST_FULFILLED = "DATA_ACCESS_REQUEST_FULFILLED"
    ERASURE_REQUEST_APPROVED = "ERASURE_REQUEST_APPROVED"
    ERASURE_REQUEST_REJECTED = "ERASURE_REQUEST_REJECTED"
    # A clinician/CHW searched for or opened a participant's identified record.
    CLINICIAN_PARTICIPANT_VIEWED = "CLINICIAN_PARTICIPANT_VIEWED"
    # Care-navigation referrals.
    REFERRAL_CREATED = "REFERRAL_CREATED"
    REFERRAL_STATUS_UPDATED = "REFERRAL_STATUS_UPDATED"


class ErasureJurisdiction(str, enum.Enum):
    GDPR = "GDPR"
    POPIA = "POPIA"
    NDPA = "NDPA"  # Nigeria Data Protection Act 2023 (regulator: NDPC)
    CDPA = "CDPA"  # Zimbabwe Cyber and Data Protection Act [Ch 12:07] (POTRAZ)
    OTHER = "OTHER"


class ErasureBasis(str, enum.Enum):
    DATA_SUBJECT_REQUEST = "DATA_SUBJECT_REQUEST"
    WITHDRAWN_CONSENT = "WITHDRAWN_CONSENT"
    ACCOUNT_DELETION = "ACCOUNT_DELETION"
    ADMIN_ACTION = "ADMIN_ACTION"


class ErasureTargetType(str, enum.Enum):
    USER_ACCOUNT = "USER_ACCOUNT"
    STUDY_SUBJECT = "STUDY_SUBJECT"
    CALIBRATION_RECORD = "CALIBRATION_RECORD"


class ErasureStatus(str, enum.Enum):
    PENDING = "PENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class NotificationType(str, enum.Enum):
    ERASURE_APPROVAL_REQUESTED = "ERASURE_APPROVAL_REQUESTED"
    ERASURE_REQUEST_APPROVED = "ERASURE_REQUEST_APPROVED"
    ERASURE_REQUEST_REJECTED = "ERASURE_REQUEST_REJECTED"
    REFERRAL_RAISED = "REFERRAL_RAISED"
    GENERIC = "GENERIC"


class SexAtBirth(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    INTERSEX = "INTERSEX"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


class Posture(str, enum.Enum):
    SITTING = "SITTING"
    STANDING = "STANDING"
    SUPINE = "SUPINE"
    SEMI_RECLINED = "SEMI_RECLINED"


class TimeOfDay(str, enum.Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    NIGHT = "NIGHT"


class ReferenceDeviceType(str, enum.Enum):
    PULSE_OXIMETER = "PULSE_OXIMETER"
    SMART_WATCH = "SMART_WATCH"
    ECG_STRAP = "ECG_STRAP"
    MEDICAL_ECG = "MEDICAL_ECG"
    MANUAL_PULSE_COUNT = "MANUAL_PULSE_COUNT"


class ToiQuality(str, enum.Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    POOR = "POOR"


class FitzpatrickScale(str, enum.Enum):
    I = "I"  # noqa: E741 - Fitzpatrick type I, a clinical scale label
    II = "II"
    III = "III"
    IV = "IV"
    V = "V"
    VI = "VI"


class RiskClass(str, enum.Enum):
    LOW_RISK = "LOW_RISK"
    ELEVATED_RISK = "ELEVATED_RISK"
    HIGH_RISK = "HIGH_RISK"
    VERY_HIGH_RISK = "VERY_HIGH_RISK"


class TriageState(str, enum.Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    # PII fields are nullable post-governance migration so account erasure
    # can tombstone them while preserving the row's identity for downstream
    # FKs (assessments, audit_logs, study_subjects). The lower(email) unique
    # index is partial (WHERE email IS NOT NULL) so a new account can
    # re-register a previously-erased address.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        default=UserRole.PATIENT,
        server_default=UserRole.PATIENT.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Deployment site / country this participant was enrolled under (e.g. "ZW",
    # "NG"). Stamped at registration from the instance's configured site_code.
    site_code: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="DEFAULT", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    erased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    erasure_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("erasure_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    consents: Mapped[list[ConsentRecord]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    triage_assessments: Mapped[list[TriageAssessment]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    toi_assessments: Mapped[list[ToiAssessment]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    calibration_records: Mapped[list[RppgCalibrationRecord]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    study_subjects: Mapped[list[StudySubject]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    study_sessions: Mapped[list[StudySession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="noload"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="recipient", cascade="all, delete-orphan", lazy="noload"
    )

    __table_args__ = (
        Index("ix_users_email_lower", func.lower(email), unique=True),
    )

    def active_consent_types(self) -> set[ConsentType]:
        return {c.consent_type for c in self.consents if c.revoked_at is None}


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens", lazy="joined")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        SAEnum(ConsentType, name="consent_type", native_enum=True), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="consents")

    __table_args__ = (
        UniqueConstraint("user_id", "consent_type", "version", name="uq_consent_user_type_ver"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action", native_enum=True), nullable=False, index=True
    )
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class TriageAssessment(Base):
    __tablename__ = "triage_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[TriageState] = mapped_column(
        SAEnum(TriageState, name="triage_state", native_enum=True), nullable=False
    )
    top_class: Mapped[RiskClass] = mapped_column(
        SAEnum(RiskClass, name="risk_class", native_enum=True), nullable=False
    )
    class_probabilities: Mapped[dict[str, float]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    evidence: Mapped[dict[str, float]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    vacuity: Mapped[float] = mapped_column(Float, nullable=False)
    aleatoric_uncertainty: Mapped[float] = mapped_column(Float, nullable=False)
    epistemic_uncertainty: Mapped[float] = mapped_column(Float, nullable=False)
    dirichlet_strength: Mapped[float] = mapped_column(Float, nullable=False)
    # The single-risk columns above hold the *overall summary* (the worst-state
    # disease) for backward compatibility and indexing. The authoritative,
    # independently-weighted per-disease breakdown lives here as a list of
    # serialized ``PerDiseaseRisk`` objects (one per disease in ``DISEASES``).
    per_disease_risks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    raw_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    derived_features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    plausibility_flags: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )
    symptoms: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    safety_override_triggered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    override_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )
    model_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="triage_assessments")

    __table_args__ = (
        Index(
            "ix_triage_assessments_user_id_created_at",
            "user_id",
            "created_at",
        ),
        Index("ix_triage_assessments_state", "state"),
        CheckConstraint(
            "vacuity >= 0 AND vacuity <= 1",
            name="ck_triage_assessments_vacuity_unit",
        ),
        CheckConstraint(
            "aleatoric_uncertainty >= 0 AND epistemic_uncertainty >= 0",
            name="ck_triage_assessments_uncertainty_nonneg",
        ),
    )


class ToiAssessment(Base):
    __tablename__ = "toi_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    quality: Mapped[ToiQuality] = mapped_column(
        SAEnum(ToiQuality, name="toi_quality", native_enum=True), nullable=False
    )
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    sample_rate_hz: Mapped[float] = mapped_column(Float, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    frames_used: Mapped[int] = mapped_column(Integer, nullable=False)
    skin_tone_estimate: Mapped[FitzpatrickScale | None] = mapped_column(
        SAEnum(FitzpatrickScale, name="fitzpatrick_scale", native_enum=True),
        nullable=True,
    )
    method_selected: Mapped[str] = mapped_column(String(16), nullable=False)
    snr_chrom_db: Mapped[float] = mapped_column(Float, nullable=False)
    snr_pos_db: Mapped[float] = mapped_column(Float, nullable=False)
    motion_score: Mapped[float] = mapped_column(Float, nullable=False)
    lighting_score: Mapped[float] = mapped_column(Float, nullable=False)
    face_presence_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    heart_rate_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    heart_rate_ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    heart_rate_ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    respiratory_rate_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    respiratory_rate_ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    respiratory_rate_ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_rmssd_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_sdnn_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    stress_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    biomarkers: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    signal_quality: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    warnings: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)), nullable=False, default=list, server_default="{}"
    )
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="toi_assessments")

    __table_args__ = (
        Index(
            "ix_toi_assessments_user_id_created_at",
            "user_id",
            "created_at",
        ),
        Index("ix_toi_assessments_quality", "quality"),
        CheckConstraint(
            "motion_score >= 0 AND motion_score <= 1 "
            "AND lighting_score >= 0 AND lighting_score <= 1 "
            "AND face_presence_ratio >= 0 AND face_presence_ratio <= 1",
            name="ck_toi_assessments_quality_scores_unit",
        ),
    )


class RppgCalibrationRecord(Base):
    __tablename__ = "rppg_calibration_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    toi_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("toi_assessments.id", ondelete="SET NULL"),
        nullable=True,
    )
    reference_device_type: Mapped[ReferenceDeviceType] = mapped_column(
        SAEnum(
            ReferenceDeviceType,
            name="reference_device_type",
            native_enum=True,
        ),
        nullable=False,
    )
    reference_device_label: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    reference_hr_bpm: Mapped[float] = mapped_column(Float, nullable=False)
    reference_rr_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_hr_sample_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    reference_hrv_rmssd_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_hrv_sdnn_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_rr_intervals_ms: Mapped[list[float] | None] = mapped_column(
        JSONB, nullable=True
    )
    auto_paired_from_ble: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    rppg_hr_bpm: Mapped[float] = mapped_column(Float, nullable=False)
    rppg_rr_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    rppg_hrv_rmssd_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rppg_hrv_sdnn_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rppg_quality: Mapped[str] = mapped_column(String(16), nullable=False)
    rppg_method_selected: Mapped[str] = mapped_column(String(16), nullable=False)
    rppg_snr_chrom_db: Mapped[float] = mapped_column(Float, nullable=False)
    rppg_snr_pos_db: Mapped[float] = mapped_column(Float, nullable=False)
    rppg_pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    skin_tone_estimate: Mapped[FitzpatrickScale | None] = mapped_column(
        SAEnum(
            FitzpatrickScale,
            name="fitzpatrick_scale",
            native_enum=True,
            create_type=False,
        ),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    study_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("study_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="calibration_records")
    study_session: Mapped[StudySession | None] = relationship(
        back_populates="calibration_records", lazy="joined"
    )

    __table_args__ = (
        Index(
            "ix_rppg_calibration_user_id_created_at",
            "user_id",
            "created_at",
        ),
        Index("ix_rppg_calibration_toi_assessment_id", "toi_assessment_id"),
        Index("ix_rppg_calibration_study_session_id", "study_session_id"),
        Index("ix_rppg_calibration_auto_paired", "auto_paired_from_ble"),
        CheckConstraint(
            "reference_hr_bpm >= 30 AND reference_hr_bpm <= 240 "
            "AND rppg_hr_bpm >= 30 AND rppg_hr_bpm <= 240",
            name="ck_rppg_calibration_hr_plausible",
        ),
        CheckConstraint(
            "(reference_hrv_rmssd_ms IS NULL OR reference_hrv_rmssd_ms >= 0) AND "
            "(reference_hrv_sdnn_ms IS NULL OR reference_hrv_sdnn_ms >= 0) AND "
            "(rppg_hrv_rmssd_ms IS NULL OR rppg_hrv_rmssd_ms >= 0) AND "
            "(rppg_hrv_sdnn_ms IS NULL OR rppg_hrv_sdnn_ms >= 0)",
            name="ck_rppg_calibration_hrv_nonneg",
        ),
    )


class StudySubject(Base):
    """Anonymous study subject identified by a researcher-assigned external id.

    No PII lives here — ``external_subject_id`` is the researcher's own
    bookkeeping label (e.g. ``S001`` or ``SUBJ-2026-001``). The composite
    unique constraint ``(user_id, external_subject_id)`` lets two researchers
    each have an "S001" without collision.
    """

    __tablename__ = "study_subjects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    age_years: Mapped[int] = mapped_column(Integer, nullable=False)
    sex_assigned_at_birth: Mapped[SexAtBirth] = mapped_column(
        SAEnum(
            SexAtBirth,
            name="sex_assigned_at_birth",
            native_enum=True,
        ),
        nullable=False,
    )
    fitzpatrick_scale: Mapped[FitzpatrickScale | None] = mapped_column(
        SAEnum(
            FitzpatrickScale,
            name="fitzpatrick_scale",
            native_enum=True,
            create_type=False,
        ),
        nullable=True,
    )
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    medical_history_summary: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    consent_protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    anonymised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    erasure_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("erasure_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped[User] = relationship(back_populates="study_subjects")
    sessions: Mapped[list[StudySession]] = relationship(
        back_populates="subject",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "external_subject_id",
            name="uq_study_subjects_user_ext_id",
        ),
        Index(
            "ix_study_subjects_user_id_enrolled_at",
            "user_id",
            "enrolled_at",
        ),
        CheckConstraint(
            "age_years >= 0 AND age_years <= 130",
            name="ck_study_subjects_age",
        ),
        CheckConstraint(
            "(height_cm IS NULL OR (height_cm > 0 AND height_cm <= 250)) AND "
            "(weight_kg IS NULL OR (weight_kg > 0 AND weight_kg <= 400))",
            name="ck_study_subjects_anthropometrics",
        ),
    )


class StudySession(Base):
    """A pre-registered capture session pinned to a subject.

    Locks on first calibration capture so cohort covariates (posture, ambient
    lux, caffeine status, etc.) cannot drift mid-study. The partial unique
    index ``uq_study_sessions_active_per_user`` (created in the migration
    rather than declared here because SQLAlchemy doesn't natively model
    partial indexes on every backend) enforces at most one active session
    per researcher so the calibration auto-attach is unambiguous.
    """

    __tablename__ = "study_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    study_subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("study_subjects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    session_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    posture: Mapped[Posture] = mapped_column(
        SAEnum(Posture, name="study_posture", native_enum=True),
        nullable=False,
    )
    time_of_day: Mapped[TimeOfDay] = mapped_column(
        SAEnum(TimeOfDay, name="time_of_day", native_enum=True),
        nullable=False,
    )
    ambient_lux: Mapped[float | None] = mapped_column(Float, nullable=True)
    ambient_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    room_humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fasted_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    caffeine_within_2h: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    nicotine_within_2h: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    alcohol_within_24h: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_exercise_hours_ago: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    recording_site_label: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    protocol_version: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="study_sessions")
    subject: Mapped[StudySubject] = relationship(
        back_populates="sessions", lazy="joined"
    )
    calibration_records: Mapped[list[RppgCalibrationRecord]] = relationship(
        back_populates="study_session", lazy="noload"
    )

    __table_args__ = (
        Index(
            "ix_study_sessions_user_id_started_at",
            "user_id",
            "session_started_at",
        ),
        Index(
            "ix_study_sessions_subject_id_started_at",
            "study_subject_id",
            "session_started_at",
        ),
        CheckConstraint(
            "(ambient_lux IS NULL OR ambient_lux >= 0) AND "
            "(ambient_temperature_c IS NULL OR ambient_temperature_c BETWEEN -20 AND 60) AND "
            "(room_humidity_pct IS NULL OR room_humidity_pct BETWEEN 0 AND 100) AND "
            "(fasted_hours IS NULL OR fasted_hours BETWEEN 0 AND 72) AND "
            "(last_exercise_hours_ago IS NULL OR last_exercise_hours_ago BETWEEN 0 AND 168)",
            name="ck_study_sessions_covariate_ranges",
        ),
    )


class ErasureRequest(Base):
    """Append-only governance ledger for GDPR Art 17 / POPIA s24 erasures.

    Rows are never updated except to flip ``status`` and set ``processed_at``.
    The regulator's evidence trail lives here — even after the underlying
    PII has been tombstoned, this row proves the request was honoured.
    """

    __tablename__ = "erasure_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    requesting_actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_type: Mapped[ErasureTargetType] = mapped_column(
        SAEnum(
            ErasureTargetType,
            name="erasure_target_type",
            native_enum=True,
        ),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    jurisdiction: Mapped[ErasureJurisdiction] = mapped_column(
        SAEnum(
            ErasureJurisdiction,
            name="erasure_jurisdiction",
            native_enum=True,
        ),
        nullable=False,
    )
    request_basis: Mapped[ErasureBasis] = mapped_column(
        SAEnum(ErasureBasis, name="erasure_basis", native_enum=True),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[ErasureStatus] = mapped_column(
        SAEnum(ErasureStatus, name="erasure_status", native_enum=True),
        nullable=False,
        default=ErasureStatus.PENDING,
        server_default=ErasureStatus.PENDING.value,
    )
    statutory_retention_applied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    retention_basis: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Maker-checker: admin-initiated requests are created AWAITING_APPROVAL and
    # require a second admin to approve before execution.
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    __table_args__ = (
        Index(
            "ix_erasure_requests_target",
            "target_type",
            "target_id",
        ),
        Index("ix_erasure_requests_target_user_id", "target_user_id"),
        Index("ix_erasure_requests_status", "status"),
    )


class Notification(Base):
    """In-app notification. Append-only except for ``read_at`` flips."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type", native_enum=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    recipient: Mapped[User] = relationship(back_populates="notifications")

    __table_args__ = (
        Index(
            "ix_notifications_recipient_created_at",
            "recipient_user_id",
            "created_at",
        ),
    )


class JobStatus(str, enum.Enum):
    """Lifecycle of an inbound capture (e.g. a WhatsApp video) being processed.

    QUEUED      -> claimed by a worker -> PROCESSING
    PROCESSING  -> SUCCEEDED (vitals returned)
                -> REJECTED  (capture unusable; user asked to re-record — a
                              normal outcome, not an error)
                -> QUEUED    (transient failure, re-queued with backoff)
                -> FAILED    (max attempts exhausted)
    """

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ProcessingJob(Base):
    """A unit of asynchronous capture processing for the WhatsApp/kiosk rail.

    The webhook writes a QUEUED row and returns 200 immediately; a background
    worker (cPanel cron or persistent Python app) claims it with
    ``FOR UPDATE SKIP LOCKED``, downloads the media, runs the rPPG extractor +
    pipeline, replies, and records the terminal status. Keeping the queue in the
    primary database means no Redis/Celery dependency on shared hosting.
    """

    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status", native_enum=True),
        nullable=False,
        server_default=JobStatus.QUEUED.value,
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="WHATSAPP"
    )
    # Sender phone (E.164). For the demo we store it directly; production should
    # store a salted hash and keep the cleartext only in the session store.
    wa_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Inbound WhatsApp message id — used for idempotency (Meta re-delivers).
    wa_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # WhatsApp media id to download, and the local temp path once fetched.
    media_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="en"
    )
    # Optional participant user the result is persisted against (set by the
    # webhook once a phone number is mapped to a participant). Null in tests.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Collected demographic + symptom intake (for later NCD-3B triage compose).
    intake: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Drives the claim query: oldest eligible QUEUED job first.
        Index(
            "ix_processing_jobs_status_next_attempt",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index("ix_processing_jobs_wa_message_id", "wa_message_id"),
        CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts + 1",
            name="ck_processing_jobs_attempts_bounded",
        ),
    )


class WhatsAppSession(Base):
    """Per-phone conversation state for the WhatsApp check-up flow.

    One row per sender, keyed on the E.164 phone number. ``state`` stores the
    ``ConvState`` value as text (conversation steps evolve faster than is worth a
    native enum + migration each time). ``last_message_id`` deduplicates Meta's
    at-least-once webhook re-delivery.
    """

    __tablename__ = "whatsapp_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="LANGUAGE"
    )
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    intake: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    audit_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    safety_triggers: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )
    contextual: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )
    # Last processed inbound message id — webhook idempotency.
    last_message_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    # Pseudonymous account anchored at consent (no email/name/phone on it). Lets
    # captures persist to the clinician app and brings the participant under the
    # standard account-erasure flow. SET NULL so a tombstoned user does not
    # cascade-delete the (separately scrubbed) session.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_whatsapp_sessions_phone", "phone", unique=True),
        Index("ix_whatsapp_sessions_user_id", "user_id"),
    )


class ResearchTriageCase(Base):
    """A clinician/CHW-entered, ground-truth-LABELLED triage case for training.

    Unlike ``triage_assessments`` (model *predictions*), this stores real
    measurements + symptoms + CONFIRMED per-disease labels. Obesity and
    hypertension labels are objective (measured BMI / BP); the diabetes label is
    anchored on HbA1c / fasting glucose (the ground truth the proxy model can't
    see). Exported as the training corpus for the multi-head DANN-EDL so Model 1
    learns from recruited data, not proxies. ``capture_domain`` feeds the DANN
    domain head (CLINICAL_GRADE vs CHW_TAPE_MEASURE).
    """

    __tablename__ = "research_triage_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # Researcher who entered it; SET NULL on erasure so the de-identified case
    # is retained for research integrity.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    study_subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("study_subjects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # "CLINICAL_GRADE" | "CHW_TAPE_MEASURE" — measurement provenance (DANN domain).
    capture_domain: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="CLINICAL_GRADE"
    )
    # Deployment site / country (e.g. "ZW", "NG") — lets the training corpus be
    # stratified by geography for per-site calibration / domain adaptation.
    site_code: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="DEFAULT", index=True
    )

    # --- measured inputs (the model features) ---
    age_years: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(String(16), nullable=False)  # MALE|FEMALE|OTHER
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    waist_cm: Mapped[float] = mapped_column(Float, nullable=False)
    hip_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    systolic_bp_mmhg: Mapped[float | None] = mapped_column(Float, nullable=True)
    diastolic_bp_mmhg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- structured symptom audit (same vocabulary as Pathway A) ---
    safety_triggers: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )
    contextual: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )

    # --- diabetes ground truth (one or both) ---
    fasting_glucose_mmol_l: Mapped[float | None] = mapped_column(Float, nullable=True)
    hba1c_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- confirmed per-disease labels (the training targets) ---
    obesity_label: Mapped[RiskClass] = mapped_column(
        SAEnum(RiskClass, name="risk_class", native_enum=True), nullable=False
    )
    hypertension_label: Mapped[RiskClass] = mapped_column(
        SAEnum(RiskClass, name="risk_class", native_enum=True), nullable=False
    )
    diabetes_label: Mapped[RiskClass] = mapped_column(
        SAEnum(RiskClass, name="risk_class", native_enum=True), nullable=False
    )
    # Per-disease human-legible derivation (e.g. {"diabetes": "HbA1c 7.2% -> HIGH"}).
    label_basis: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_research_triage_cases_created_at", "created_at"),
        Index("ix_research_triage_cases_capture_domain", "capture_domain"),
    )


class ReferralUrgency(str, enum.Enum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    EMERGENCY = "EMERGENCY"


class ReferralStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReferralDestinationType(str, enum.Enum):
    VICTUS_FACILITY = "VICTUS_FACILITY"
    PRIMARY_HEALTH_CENTRE = "PRIMARY_HEALTH_CENTRE"  # public PHC (e.g. Nigeria)
    PUBLIC_CLINIC = "PUBLIC_CLINIC"
    HOSPITAL = "HOSPITAL"
    TEACHING_HOSPITAL = "TEACHING_HOSPITAL"  # tertiary referral hospital
    OTHER = "OTHER"


class Referral(Base):
    """A care-navigation referral: a CHW/clinician directs a participant to a
    destination (a Victus facility or an external clinic/hospital), optionally
    linked to the triage assessment that prompted it, with a tracked status."""

    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # The referred participant. CASCADE: a referral is meaningless once the
    # participant account is hard-deleted.
    participant_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The clinician/CHW who raised it; SET NULL on their erasure (the referral
    # itself stays, for the participant's care record).
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Optional provenance: the Pathway A assessment that flagged the referral.
    source_triage_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage_assessments.id", ondelete="SET NULL"),
        nullable=True,
    )

    destination_type: Mapped[ReferralDestinationType] = mapped_column(
        SAEnum(ReferralDestinationType, name="referral_destination_type", native_enum=True),
        nullable=False,
    )
    destination_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    urgency: Mapped[ReferralUrgency] = mapped_column(
        SAEnum(ReferralUrgency, name="referral_urgency", native_enum=True), nullable=False
    )
    status: Mapped[ReferralStatus] = mapped_column(
        SAEnum(ReferralStatus, name="referral_status", native_enum=True),
        nullable=False,
        server_default=ReferralStatus.PENDING.value,
    )
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_referrals_participant_created", "participant_user_id", "created_at"
        ),
    )
