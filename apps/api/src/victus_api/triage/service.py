"""3B-Triage orchestration.

Pipeline order — every step is intentional:

    1. Deterministic safety overrides     (RED short-circuit; no inference)
    2. Cross-field plausibility flags     (informs YELLOW)
    3. Feature engineering + EDL inference
    4. State-machine decision              (GREEN/YELLOW/RED)
    5. Persist assessment + audit log
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    User,
)
from victus_api.db.models import RiskClass as DbRiskClass
from victus_api.db.models import (
    TriageAssessment as TriageAssessmentRow,
)
from victus_api.db.models import TriageState as DbTriageState
from victus_api.triage.edl.inference import EvidentialPrediction, get_predictor
from victus_api.triage.features import DerivedFeatures as DerivedFromFeatures
from victus_api.triage.features import compute_derived
from victus_api.triage.safety import evaluate_safety_overrides
from victus_api.triage.schemas import (
    RISK_CLASSES,
    PlausibilityFlag,
    RiskClass,
    TriageAssessmentRequest,
    TriageAssessmentResponse,
    TriageState,
    TriageUncertainty,
)
from victus_api.triage.schemas import (
    DerivedFeatures as DerivedSchema,
)
from victus_api.triage.validation import detect_plausibility_flags

log = get_logger(__name__)


# --- State machine -----------------------------------------------------------

VACUITY_YELLOW_THRESHOLD: float = 0.5
CONFIDENCE_RED_THRESHOLD: float = 0.6
RED_RISK_CLASSES: frozenset[RiskClass] = frozenset(
    {RiskClass.HIGH_RISK, RiskClass.VERY_HIGH_RISK}
)


@dataclass(frozen=True, slots=True)
class StateDecision:
    state: TriageState
    rationale: str
    next_action: str


def decide_state(
    prediction: EvidentialPrediction,
    plausibility_flags: list[PlausibilityFlag],
    *,
    safety_override_triggered: bool,
) -> StateDecision:
    if safety_override_triggered:
        return StateDecision(
            TriageState.RED,
            "Deterministic safety override matched — clinical-referral pathway.",
            "immediate_clinical_referral",
        )

    if plausibility_flags:
        return StateDecision(
            TriageState.YELLOW,
            f"Plausibility flag(s) raised: {', '.join(f.value for f in plausibility_flags)}. "
            "Recommend unit-correction recheck and symptom audit.",
            "unit_correction_recheck",
        )

    top_prob = prediction.expected_probs[prediction.top_class]
    if (
        prediction.top_class in RED_RISK_CLASSES
        and prediction.vacuity < VACUITY_YELLOW_THRESHOLD
        and top_prob >= CONFIDENCE_RED_THRESHOLD
    ):
        return StateDecision(
            TriageState.RED,
            f"High-confidence high-risk classification "
            f"(p({prediction.top_class.value})={top_prob:.2f}, u={prediction.vacuity:.2f}).",
            "clinical_referral",
        )

    if prediction.vacuity >= VACUITY_YELLOW_THRESHOLD:
        return StateDecision(
            TriageState.YELLOW,
            f"High epistemic uncertainty (u={prediction.vacuity:.2f}) — "
            "OOD profile; running symptom-audit fallback.",
            "symptom_audit_fallback",
        )

    if prediction.top_class in RED_RISK_CLASSES:
        return StateDecision(
            TriageState.YELLOW,
            f"Elevated risk class with sub-threshold confidence "
            f"(p={top_prob:.2f}); recommending clinician review.",
            "clinician_review",
        )

    return StateDecision(
        TriageState.GREEN,
        f"Low-risk classification (p({prediction.top_class.value})={top_prob:.2f}, "
        f"u={prediction.vacuity:.2f}). Routine follow-up.",
        "routine_followup",
    )


STATE_TO_AUDIT_ACTION: dict[TriageState, AuditAction] = {
    TriageState.GREEN: AuditAction.PATHWAY_A_RESULT_GREEN,
    TriageState.YELLOW: AuditAction.PATHWAY_A_RESULT_YELLOW,
    TriageState.RED: AuditAction.PATHWAY_A_RESULT_RED,
}


# --- Public service ----------------------------------------------------------


async def assess_triage(
    db: AsyncSession,
    *,
    user: User,
    payload: TriageAssessmentRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> TriageAssessmentResponse:
    # 1. Deterministic safety overrides — short-circuit before any inference.
    safety = evaluate_safety_overrides(payload.symptoms)

    derived = compute_derived(payload.inputs)
    plausibility_flags: list[PlausibilityFlag] = (
        [] if safety.triggered else detect_plausibility_flags(payload.inputs)
    )

    if safety.triggered:
        prediction = _safety_override_prediction()
    else:
        predictor = get_predictor()
        prediction = predictor.predict(payload.inputs, derived)

    decision = decide_state(
        prediction,
        plausibility_flags,
        safety_override_triggered=safety.triggered,
    )

    # 2. Persist assessment.
    row = TriageAssessmentRow(
        user_id=user.id,
        state=DbTriageState(decision.state.value),
        top_class=DbRiskClass(prediction.top_class.value),
        class_probabilities={k.value: v for k, v in prediction.expected_probs.items()},
        evidence={k.value: v for k, v in prediction.evidence.items()},
        vacuity=prediction.vacuity,
        aleatoric_uncertainty=prediction.aleatoric,
        epistemic_uncertainty=prediction.epistemic,
        dirichlet_strength=prediction.strength,
        raw_inputs=_jsonable_inputs(payload),
        derived_features=_jsonable_derived(derived),
        plausibility_flags=[f.value for f in plausibility_flags],
        symptoms={
            "safety_triggers": list(payload.symptoms.safety_triggers),
            "contextual": list(payload.symptoms.contextual),
        },
        safety_override_triggered=safety.triggered,
        override_reasons=list(safety.reasons),
        model_kind=prediction.model_kind,
        model_version=prediction.model_version,
    )
    db.add(row)
    await db.flush()

    # 3. Audit trail — result event plus a dedicated override event when applicable.
    base_metadata: dict[str, Any] = {
        "assessment_id": str(row.id),
        "model_kind": prediction.model_kind,
        "model_version": prediction.model_version,
        "top_class": prediction.top_class.value,
        "vacuity": round(prediction.vacuity, 4),
        "rationale": decision.rationale,
    }
    if plausibility_flags:
        base_metadata["plausibility_flags"] = [f.value for f in plausibility_flags]

    await write_audit(
        db,
        action=STATE_TO_AUDIT_ACTION[decision.state],
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"triage:assessment:{row.id}",
        metadata=base_metadata,
    )
    if safety.triggered:
        await write_audit(
            db,
            action=AuditAction.PATHWAY_A_SAFETY_OVERRIDE,
            actor_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource=f"triage:assessment:{row.id}",
            metadata={
                "assessment_id": str(row.id),
                "override_reasons": list(safety.reasons),
            },
        )

    log.info(
        "triage_assessment_completed",
        assessment_id=str(row.id),
        state=decision.state.value,
        top_class=prediction.top_class.value,
        vacuity=round(prediction.vacuity, 4),
        safety_override=safety.triggered,
    )

    return _to_response(
        row=row,
        prediction=prediction,
        derived=derived,
        plausibility_flags=plausibility_flags,
        decision=decision,
        override_reasons=list(safety.reasons),
    )


async def list_assessments_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 25,
) -> list[TriageAssessmentResponse]:
    stmt = (
        select(TriageAssessmentRow)
        .where(TriageAssessmentRow.user_id == user_id)
        .order_by(desc(TriageAssessmentRow.created_at))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    return [_row_to_response(row) for row in rows]


# --- Helpers -----------------------------------------------------------------


def _safety_override_prediction() -> EvidentialPrediction:
    """Synthesize a Dirichlet output consistent with the RED override.

    All probability mass on VERY_HIGH_RISK, very low vacuity. This is *not*
    a model prediction — it documents the deterministic override in the same
    shape as a real inference so the downstream UI and audit fields populate
    correctly.
    """
    from victus_api.triage.edl.inference import finalize_prediction

    evidence = [0.0, 0.0, 0.0, 100.0]
    return finalize_prediction(
        evidence,
        model_kind="deterministic_safety_override",
        model_version="1.0.0",
    )


def _jsonable_inputs(payload: TriageAssessmentRequest) -> dict[str, Any]:
    return {
        "height_cm": payload.inputs.height_cm,
        "weight_kg": payload.inputs.weight_kg,
        "waist_cm": payload.inputs.waist_cm,
        "hip_cm": payload.inputs.hip_cm,
        "age_years": payload.inputs.age_years,
        "sex": payload.inputs.sex.value,
        "systolic_bp_mmhg": payload.inputs.systolic_bp_mmhg,
        "diastolic_bp_mmhg": payload.inputs.diastolic_bp_mmhg,
    }


def _jsonable_derived(derived: DerivedFromFeatures) -> dict[str, float | None]:
    return {
        "bmi": derived.bmi,
        "whtr": derived.whtr,
        "whr": derived.whr,
        "pulse_pressure_mmhg": derived.pulse_pressure_mmhg,
    }


def _to_response(
    *,
    row: TriageAssessmentRow,
    prediction: EvidentialPrediction,
    derived: DerivedFromFeatures,
    plausibility_flags: list[PlausibilityFlag],
    decision: StateDecision,
    override_reasons: list[str],
) -> TriageAssessmentResponse:
    return TriageAssessmentResponse(
        id=row.id,
        state=decision.state,
        top_class=prediction.top_class,
        class_probabilities={cls: prediction.expected_probs[cls] for cls in RISK_CLASSES},
        evidence={cls: prediction.evidence[cls] for cls in RISK_CLASSES},
        uncertainty=TriageUncertainty(
            vacuity=prediction.vacuity,
            aleatoric=prediction.aleatoric,
            epistemic=prediction.epistemic,
            strength=prediction.strength,
        ),
        derived_features=DerivedSchema(
            bmi=derived.bmi,
            whtr=derived.whtr,
            whr=derived.whr,
            pulse_pressure_mmhg=derived.pulse_pressure_mmhg,
        ),
        plausibility_flags=plausibility_flags,
        safety_override_triggered=row.safety_override_triggered,
        override_reasons=override_reasons,
        model_kind=prediction.model_kind,
        next_action=decision.next_action,
        created_at=row.created_at,
    )


def _row_to_response(row: TriageAssessmentRow) -> TriageAssessmentResponse:
    expected_probs = {
        RiskClass(cls): float(p) for cls, p in row.class_probabilities.items()
    }
    top_class = RiskClass(row.top_class.value)
    derived = DerivedSchema(
        bmi=row.derived_features.get("bmi"),
        whtr=row.derived_features.get("whtr"),
        whr=row.derived_features.get("whr"),
        pulse_pressure_mmhg=row.derived_features.get("pulse_pressure_mmhg"),
    )
    return TriageAssessmentResponse(
        id=row.id,
        state=TriageState(row.state.value),
        top_class=top_class,
        class_probabilities={cls: expected_probs.get(cls, 0.0) for cls in RISK_CLASSES},
        evidence={
            cls: float(row.evidence.get(cls.value, 0.0)) for cls in RISK_CLASSES
        },
        uncertainty=TriageUncertainty(
            vacuity=row.vacuity,
            aleatoric=row.aleatoric_uncertainty,
            epistemic=row.epistemic_uncertainty,
            strength=row.dirichlet_strength,
        ),
        derived_features=derived,
        plausibility_flags=[PlausibilityFlag(f) for f in row.plausibility_flags],
        safety_override_triggered=row.safety_override_triggered,
        override_reasons=list(row.override_reasons),
        model_kind=row.model_kind,
        next_action="(historical)",
        created_at=row.created_at,
    )
