"""Active-learning acquisition scorer — pure, no DB."""

from __future__ import annotations

from victus_api.triage.acquisition import (
    AcquisitionPriority,
    score_assessment,
)
from victus_api.triage.schemas import (
    Disease,
    PerDiseaseRisk,
    RiskClass,
    TriageState,
    TriageUncertainty,
)


def _risk(
    disease: Disease,
    *,
    vacuity: float,
    probs: dict[RiskClass, float],
) -> PerDiseaseRisk:
    top = max(probs, key=lambda k: probs[k])
    return PerDiseaseRisk(
        disease=disease,
        state=TriageState.YELLOW,
        top_class=top,
        class_probabilities=probs,
        evidence={k: v * 10 for k, v in probs.items()},
        uncertainty=TriageUncertainty(
            vacuity=vacuity, aleatoric=0.1, epistemic=0.1, strength=10.0
        ),
        contributing_factors=[],
        next_action="clinician_review",
    )


_NARROW = {
    RiskClass.LOW_RISK: 0.12,
    RiskClass.ELEVATED_RISK: 0.40,
    RiskClass.HIGH_RISK: 0.38,
    RiskClass.VERY_HIGH_RISK: 0.10,
}  # top-two margin ~0.02 → boundary proximity ~0.98
_CONFIDENT = {
    RiskClass.LOW_RISK: 0.90,
    RiskClass.ELEVATED_RISK: 0.05,
    RiskClass.HIGH_RISK: 0.03,
    RiskClass.VERY_HIGH_RISK: 0.02,
}  # top-two margin 0.85 → boundary proximity 0.15


def test_uncertain_boundary_diabetes_is_high_priority() -> None:
    score = score_assessment([_risk(Disease.DIABETES, vacuity=0.7, probs=_NARROW)])
    assert score is not None
    assert score.driving_disease is Disease.DIABETES
    assert score.priority is AcquisitionPriority.HIGH
    assert score.acquisition_score > 0.66
    assert "HbA1c" in score.confirmatory_test


def test_confident_case_is_low_priority() -> None:
    score = score_assessment(
        [_risk(Disease.DIABETES, vacuity=0.05, probs=_CONFIDENT)]
    )
    assert score is not None
    assert score.priority is AcquisitionPriority.LOW
    assert score.acquisition_score < 0.40


def test_only_deterministic_diseases_yield_no_acquisition() -> None:
    # Obesity/hypertension are confirmed by a tape measure / cuff, not a lab —
    # they are not the scarce resource, so there is nothing to ration.
    out = score_assessment(
        [
            _risk(Disease.OBESITY, vacuity=0.9, probs=_NARROW),
            _risk(Disease.HYPERTENSION, vacuity=0.9, probs=_NARROW),
        ]
    )
    assert out is None


def test_acquisition_is_driven_by_the_lab_confirmed_head() -> None:
    # A very uncertain obesity head must not inflate the score; only diabetes
    # (lab-confirmed) drives it.
    score = score_assessment(
        [
            _risk(Disease.OBESITY, vacuity=0.99, probs=_NARROW),
            _risk(Disease.DIABETES, vacuity=0.05, probs=_CONFIDENT),
        ]
    )
    assert score is not None
    assert score.driving_disease is Disease.DIABETES
    assert score.priority is AcquisitionPriority.LOW


def test_components_are_reported_and_bounded() -> None:
    score = score_assessment([_risk(Disease.DIABETES, vacuity=0.5, probs=_NARROW)])
    assert score is not None
    assert 0.0 <= score.epistemic_component <= 1.0
    assert 0.0 <= score.boundary_component <= 1.0
    assert 0.0 <= score.acquisition_score <= 1.0
