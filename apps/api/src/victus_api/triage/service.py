"""3B-Triage orchestration — per-disease evidential weighting.

Each NCD (obesity, hypertension, diabetes) is weighted independently: its own
Dirichlet, its own uncertainty decomposition and its own GREEN/YELLOW/RED
state. The overall referral state is the worst of the three, with deterministic
safety overrides forcing it (and the implicated disease) to RED.

Pipeline order — every step is intentional:

    1. Deterministic safety overrides     (force overall + mapped disease RED)
    2. Cross-field plausibility flags      (informs per-disease YELLOW)
    3. Feature engineering + per-disease EDL inference
    4. Per-disease state machine            (then overall = worst)
    5. Persist assessment + audit log
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.config import Settings
from victus_api.core.claims import (
    RESEARCH_NEXT_ACTION,
    RESEARCH_PER_DISEASE_ACTION,
    ClaimsMode,
    disclaimer_for,
    resolve_claims_mode,
)
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
from victus_api.triage.edl.inference import (
    EvidentialPrediction,
    MultiDiseasePrediction,
    get_predictor,
)
from victus_api.triage.features import DerivedFeatures as DerivedFromFeatures
from victus_api.triage.features import compute_derived
from victus_api.triage.safety import evaluate_safety_overrides
from victus_api.triage.schemas import (
    DISEASES,
    RISK_CLASSES,
    SAFETY_OVERRIDE_DISEASE,
    Disease,
    PerDiseaseRisk,
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

STATE_SEVERITY: dict[TriageState, int] = {
    TriageState.GREEN: 0,
    TriageState.YELLOW: 1,
    TriageState.RED: 2,
}

# Which disease(s) a measurement-quality plausibility flag undermines. A flag
# that makes a disease's inputs untrustworthy forces that disease to YELLOW.
PLAUSIBILITY_DISEASE_MAP: dict[PlausibilityFlag, frozenset[Disease]] = {
    PlausibilityFlag.BMI_OUT_OF_RANGE: frozenset({Disease.OBESITY, Disease.DIABETES}),
    PlausibilityFlag.WAIST_GT_HEIGHT: frozenset({Disease.OBESITY, Disease.DIABETES}),
    PlausibilityFlag.WAIST_TOO_SMALL: frozenset({Disease.OBESITY, Disease.DIABETES}),
    PlausibilityFlag.BP_INVERTED: frozenset({Disease.HYPERTENSION}),
    PlausibilityFlag.BP_EXTREME: frozenset({Disease.HYPERTENSION}),
    PlausibilityFlag.POSSIBLE_UNIT_CONFUSION_HEIGHT: frozenset(
        {Disease.OBESITY, Disease.DIABETES}
    ),
    PlausibilityFlag.POSSIBLE_UNIT_CONFUSION_WEIGHT: frozenset(
        {Disease.OBESITY, Disease.DIABETES}
    ),
}


@dataclass(frozen=True, slots=True)
class StateDecision:
    state: TriageState
    rationale: str
    next_action: str


@dataclass(frozen=True, slots=True)
class DiseaseOutcome:
    disease: Disease
    prediction: EvidentialPrediction
    state: TriageState
    next_action: str
    rationale: str
    contributing_factors: list[str] = field(default_factory=list)


def decide_disease_state(
    disease: Disease,
    prediction: EvidentialPrediction,
    disease_plausibility_flags: list[PlausibilityFlag],
    *,
    forced_red: bool,
) -> StateDecision:
    """Map one disease's Dirichlet prediction to a GREEN/YELLOW/RED state.

    Identical evidential logic to the prior single-risk machine, applied to
    each disease's own Dirichlet. ``forced_red`` carries a deterministic safety
    override that implicates this specific disease.
    """
    label = disease.value.title()

    if forced_red:
        return StateDecision(
            TriageState.RED,
            f"{label}: deterministic safety override matched — clinical-referral pathway.",
            "immediate_clinical_referral",
        )

    if disease_plausibility_flags:
        flags = ", ".join(f.value for f in disease_plausibility_flags)
        return StateDecision(
            TriageState.YELLOW,
            f"{label}: plausibility flag(s) raised ({flags}); recommend "
            "unit-correction recheck.",
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
            f"{label}: high-confidence high-risk classification "
            f"(p({prediction.top_class.value})={top_prob:.2f}, u={prediction.vacuity:.2f}).",
            "clinical_referral",
        )

    if prediction.vacuity >= VACUITY_YELLOW_THRESHOLD:
        return StateDecision(
            TriageState.YELLOW,
            f"{label}: high epistemic uncertainty (u={prediction.vacuity:.2f}) — "
            "OOD/proxy-limited profile; recommend confirmatory measurement.",
            "symptom_audit_fallback",
        )

    if prediction.top_class in RED_RISK_CLASSES:
        return StateDecision(
            TriageState.YELLOW,
            f"{label}: elevated risk class with sub-threshold confidence "
            f"(p={top_prob:.2f}); recommending clinician review.",
            "clinician_review",
        )

    return StateDecision(
        TriageState.GREEN,
        f"{label}: low-risk classification (p({prediction.top_class.value})={top_prob:.2f}, "
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
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> TriageAssessmentResponse:
    # 1. Deterministic safety overrides — matched red-flag symptom keys.
    safety = evaluate_safety_overrides(payload.symptoms)
    forced_red_diseases: set[Disease] = {
        SAFETY_OVERRIDE_DISEASE[key]
        for key in safety.reasons
        if key in SAFETY_OVERRIDE_DISEASE
    }
    safety_factors: dict[Disease, list[str]] = {}
    for key in safety.reasons:
        disease = SAFETY_OVERRIDE_DISEASE.get(key)
        if disease is not None:
            safety_factors.setdefault(disease, []).append(_humanize_safety(key))

    # 2. Derived features + plausibility (suppressed under safety override, as
    #    the override already routes to immediate referral).
    derived = compute_derived(payload.inputs)
    plausibility_flags: list[PlausibilityFlag] = (
        [] if safety.triggered else detect_plausibility_flags(payload.inputs)
    )

    # 3. Per-disease evidential inference (one Dirichlet per disease).
    predictor = get_predictor()
    contextual = frozenset(payload.symptoms.contextual)
    multi: MultiDiseasePrediction = predictor.predict(payload.inputs, derived, contextual)

    # 4. Per-disease state machine.
    outcomes: list[DiseaseOutcome] = []
    for disease in DISEASES:
        prediction = multi.per_disease[disease]
        disease_flags = [
            f
            for f in plausibility_flags
            if disease in PLAUSIBILITY_DISEASE_MAP.get(f, frozenset())
        ]
        decision = decide_disease_state(
            disease,
            prediction,
            disease_flags,
            forced_red=disease in forced_red_diseases,
        )
        factors = [*safety_factors.get(disease, []), *multi.contributing_factors[disease]]
        outcomes.append(
            DiseaseOutcome(
                disease=disease,
                prediction=prediction,
                state=decision.state,
                next_action=decision.next_action,
                rationale=decision.rationale,
                contributing_factors=factors,
            )
        )

    overall_state = _overall_state(outcomes, safety_triggered=safety.triggered)
    overall = _pick_overall(outcomes)
    overall_next_action = (
        "immediate_clinical_referral" if safety.triggered else overall.next_action
    )
    per_disease_risks = [_to_per_disease_risk(o) for o in outcomes]

    # 5. Persist. Legacy single-risk columns hold the overall summary (worst
    #    disease) for indexing/back-compat; per_disease_risks is authoritative.
    row = TriageAssessmentRow(
        user_id=user.id,
        state=DbTriageState(overall_state.value),
        top_class=DbRiskClass(overall.prediction.top_class.value),
        class_probabilities={
            k.value: v for k, v in overall.prediction.expected_probs.items()
        },
        evidence={k.value: v for k, v in overall.prediction.evidence.items()},
        vacuity=overall.prediction.vacuity,
        aleatoric_uncertainty=overall.prediction.aleatoric,
        epistemic_uncertainty=overall.prediction.epistemic,
        dirichlet_strength=overall.prediction.strength,
        per_disease_risks=[r.model_dump(mode="json") for r in per_disease_risks],
        raw_inputs=_jsonable_inputs(payload),
        derived_features=_jsonable_derived(derived),
        plausibility_flags=[f.value for f in plausibility_flags],
        symptoms={
            "safety_triggers": list(payload.symptoms.safety_triggers),
            "contextual": list(payload.symptoms.contextual),
        },
        safety_override_triggered=safety.triggered,
        override_reasons=list(safety.reasons),
        model_kind=multi.model_kind,
        model_version=multi.model_version,
    )
    db.add(row)
    await db.flush()

    # 6. Audit trail — overall result event plus a dedicated override event.
    base_metadata: dict[str, Any] = {
        "assessment_id": str(row.id),
        "model_kind": multi.model_kind,
        "model_version": multi.model_version,
        "overall_state": overall_state.value,
        "per_disease": {
            o.disease.value: {
                "state": o.state.value,
                "top_class": o.prediction.top_class.value,
                "vacuity": round(o.prediction.vacuity, 4),
            }
            for o in outcomes
        },
    }
    if plausibility_flags:
        base_metadata["plausibility_flags"] = [f.value for f in plausibility_flags]

    await write_audit(
        db,
        action=STATE_TO_AUDIT_ACTION[overall_state],
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
                "implicated_diseases": sorted(d.value for d in forced_red_diseases),
            },
        )

    log.info(
        "triage_assessment_completed",
        assessment_id=str(row.id),
        overall_state=overall_state.value,
        per_disease={o.disease.value: o.state.value for o in outcomes},
        safety_override=safety.triggered,
    )

    return _to_response(
        row=row,
        per_disease_risks=per_disease_risks,
        overall_state=overall_state,
        derived=derived,
        plausibility_flags=plausibility_flags,
        override_reasons=list(safety.reasons),
        model_kind=multi.model_kind,
        next_action=overall_next_action,
        mode=resolve_claims_mode(settings),
    )


async def list_assessments_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    settings: Settings,
    limit: int = 25,
) -> list[TriageAssessmentResponse]:
    stmt = (
        select(TriageAssessmentRow)
        .where(TriageAssessmentRow.user_id == user_id)
        .order_by(desc(TriageAssessmentRow.created_at))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    mode = resolve_claims_mode(settings)
    return [_row_to_response(row, mode=mode) for row in rows]


# --- Helpers -----------------------------------------------------------------


def _humanize_safety(key: str) -> str:
    return "Red-flag symptom: " + key.replace("_", " ")


def _overall_state(
    outcomes: list[DiseaseOutcome], *, safety_triggered: bool
) -> TriageState:
    if safety_triggered:
        return TriageState.RED
    return max(
        (o.state for o in outcomes),
        key=lambda s: STATE_SEVERITY[s],
        default=TriageState.GREEN,
    )


def _pick_overall(outcomes: list[DiseaseOutcome]) -> DiseaseOutcome:
    """The worst disease: by state severity, then top-class severity, then
    confidence. Used to populate the legacy single-risk summary columns."""
    return max(
        outcomes,
        key=lambda o: (
            STATE_SEVERITY[o.state],
            RISK_CLASSES.index(o.prediction.top_class),
            o.prediction.expected_probs[o.prediction.top_class],
        ),
    )


def _to_per_disease_risk(outcome: DiseaseOutcome) -> PerDiseaseRisk:
    prediction = outcome.prediction
    return PerDiseaseRisk(
        disease=outcome.disease,
        state=outcome.state,
        top_class=prediction.top_class,
        class_probabilities={cls: prediction.expected_probs[cls] for cls in RISK_CLASSES},
        evidence={cls: prediction.evidence[cls] for cls in RISK_CLASSES},
        uncertainty=TriageUncertainty(
            vacuity=prediction.vacuity,
            aleatoric=prediction.aleatoric,
            epistemic=prediction.epistemic,
            strength=prediction.strength,
        ),
        contributing_factors=outcome.contributing_factors,
        next_action=outcome.next_action,
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


def _apply_gate(
    *,
    mode: ClaimsMode,
    safety_triggered: bool,
    next_action: str,
    per_disease: list[PerDiseaseRisk],
) -> tuple[bool, str, str, list[PerDiseaseRisk]]:
    """Enforce the clinical-claims gate on a patient-facing result.

    Returns ``(authorised, disclaimer, next_action, per_disease)``. In research
    mode the model-derived actionable directives are stripped so no surface can
    present the risk state as clinical advice — but a deterministic red-flag
    safety override keeps its emergency guidance (conservative first-aid, not a
    model claim).
    """
    disclaimer = disclaimer_for(mode)
    if mode is ClaimsMode.CLINICAL:
        return True, disclaimer, next_action, per_disease
    gated_next = next_action if safety_triggered else RESEARCH_NEXT_ACTION
    gated_pd = [
        d.model_copy(update={"next_action": RESEARCH_PER_DISEASE_ACTION})
        for d in per_disease
    ]
    return False, disclaimer, gated_next, gated_pd


def _to_response(
    *,
    row: TriageAssessmentRow,
    per_disease_risks: list[PerDiseaseRisk],
    overall_state: TriageState,
    derived: DerivedFromFeatures,
    plausibility_flags: list[PlausibilityFlag],
    override_reasons: list[str],
    model_kind: str,
    next_action: str,
    mode: ClaimsMode,
) -> TriageAssessmentResponse:
    authorised, disclaimer, gated_next, gated_pd = _apply_gate(
        mode=mode,
        safety_triggered=row.safety_override_triggered,
        next_action=next_action,
        per_disease=per_disease_risks,
    )
    return TriageAssessmentResponse(
        id=row.id,
        overall_state=overall_state,
        per_disease=gated_pd,
        derived_features=DerivedSchema(
            bmi=derived.bmi,
            whtr=derived.whtr,
            whr=derived.whr,
            pulse_pressure_mmhg=derived.pulse_pressure_mmhg,
        ),
        plausibility_flags=plausibility_flags,
        safety_override_triggered=row.safety_override_triggered,
        override_reasons=override_reasons,
        model_kind=model_kind,
        next_action=gated_next,
        claims_mode=mode,
        clinical_claims_authorised=authorised,
        disclaimer=disclaimer,
        created_at=row.created_at,
    )


def _row_to_response(
    row: TriageAssessmentRow, *, mode: ClaimsMode
) -> TriageAssessmentResponse:
    per_disease = [
        PerDiseaseRisk.model_validate(entry) for entry in (row.per_disease_risks or [])
    ]
    derived = DerivedSchema(
        bmi=row.derived_features.get("bmi"),
        whtr=row.derived_features.get("whtr"),
        whr=row.derived_features.get("whr"),
        pulse_pressure_mmhg=row.derived_features.get("pulse_pressure_mmhg"),
    )
    authorised, disclaimer, gated_next, gated_pd = _apply_gate(
        mode=mode,
        safety_triggered=row.safety_override_triggered,
        next_action="(historical)",
        per_disease=per_disease,
    )
    return TriageAssessmentResponse(
        id=row.id,
        overall_state=TriageState(row.state.value),
        per_disease=gated_pd,
        derived_features=derived,
        plausibility_flags=[PlausibilityFlag(f) for f in row.plausibility_flags],
        safety_override_triggered=row.safety_override_triggered,
        override_reasons=list(row.override_reasons),
        model_kind=row.model_kind,
        next_action=gated_next,
        claims_mode=mode,
        clinical_claims_authorised=authorised,
        disclaimer=disclaimer,
        created_at=row.created_at,
    )
