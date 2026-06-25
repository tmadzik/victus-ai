"""Unit tests for the clinician participant-record PDF builder (no DB, no HTTP).

Exercises the reportlab flow with both an empty record and a fully-populated one
(triage per-disease table + GREEN/YELLOW/RED chip, TOI biomarker table), asserting
valid PDF bytes come back.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from victus_api.clinical.report import build_participant_report_pdf
from victus_api.clinical.schemas import ParticipantHistory, ParticipantSummary
from victus_api.db.models import User, UserRole
from victus_api.toi.schemas import (
    BiomarkerEstimate,
    SignalQuality,
    ToiAssessmentResponse,
    ToiQuality,
)
from victus_api.triage.schemas import (
    DerivedFeatures,
    Disease,
    PerDiseaseRisk,
    RiskClass,
    TriageAssessmentResponse,
    TriageState,
    TriageUncertainty,
)


def _actor() -> User:
    return User(
        role=UserRole.CLINICIAN,
        full_name="Dr Ada",
        email="ada@clinic.org",
        is_active=True,
        site_code="NG",
    )


def _summary(triage_n: int = 0, toi_n: int = 0) -> ParticipantSummary:
    return ParticipantSummary(
        user_id=uuid.uuid4(),
        email="participant@example.org",
        full_name="Test Participant",
        role="PATIENT",
        is_active=True,
        site_code="NG",
        triage_count=triage_n,
        toi_count=toi_n,
        last_activity=datetime.now(UTC),
    )


def _triage() -> TriageAssessmentResponse:
    return TriageAssessmentResponse(
        id=uuid.uuid4(),
        overall_state=TriageState.RED,
        per_disease=[
            PerDiseaseRisk(
                disease=Disease.DIABETES,
                state=TriageState.RED,
                top_class=RiskClass.HIGH_RISK,
                class_probabilities={RiskClass.HIGH_RISK: 0.8},
                evidence={RiskClass.HIGH_RISK: 12.0},
                uncertainty=TriageUncertainty(
                    vacuity=0.1, aleatoric=0.2, epistemic=0.05, strength=20.0
                ),
                contributing_factors=["polydipsia"],
                next_action="Refer for fasting glucose / HbA1c.",
            )
        ],
        derived_features=DerivedFeatures(
            bmi=31.2, whtr=0.62, whr=0.98, pulse_pressure_mmhg=55.0
        ),
        plausibility_flags=[],
        safety_override_triggered=True,
        override_reasons=["polydipsia_unquenchable_thirst"],
        model_kind="rule_based",
        next_action="Refer.",
        created_at=datetime.now(UTC),
    )


def _toi() -> ToiAssessmentResponse:
    return ToiAssessmentResponse(
        id=uuid.uuid4(),
        quality=ToiQuality.GOOD,
        duration_s=30.0,
        sample_rate_hz=30.0,
        frame_count=900,
        biomarkers={
            "heart_rate": BiomarkerEstimate(value=72.0, unit="bpm"),
            "respiratory_rate": BiomarkerEstimate(
                value=16.0, unit="brpm", experimental=True
            ),
        },
        signal_quality=SignalQuality(
            snr_chrom_db=8.0,
            snr_pos_db=7.0,
            method_selected="chrom",
            motion_score=0.9,
            lighting_score=0.8,
            face_presence_ratio=0.95,
            frames_used=880,
        ),
        method_details={},
        warnings=["low light in final segment"],
        next_action="Routine.",
        pipeline_version="v1",
        created_at=datetime.now(UTC),
    )


def test_build_pdf_empty_history() -> None:
    history = ParticipantHistory(participant=_summary(), triage=[], toi=[])
    pdf = build_participant_report_pdf(
        history, generated_by=_actor(), generated_at=datetime.now(UTC)
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_build_pdf_populated_history() -> None:
    history = ParticipantHistory(
        participant=_summary(triage_n=1, toi_n=1),
        triage=[_triage()],
        toi=[_toi()],
    )
    pdf = build_participant_report_pdf(
        history, generated_by=_actor(), generated_at=datetime.now(UTC)
    )
    assert pdf[:4] == b"%PDF"
    # Populated record renders more content than the empty one.
    assert len(pdf) > 3000
