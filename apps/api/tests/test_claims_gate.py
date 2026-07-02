"""Clinical-claims gate — config resolution + the response transform (no DB)."""

from __future__ import annotations

from victus_api.config import Settings
from victus_api.core.claims import (
    CLINICAL_DISCLAIMER,
    RESEARCH_DISCLAIMER,
    RESEARCH_NEXT_ACTION,
    RESEARCH_PER_DISEASE_ACTION,
    ClaimsMode,
    resolve_claims_mode,
)
from victus_api.triage.schemas import (
    Disease,
    PerDiseaseRisk,
    RiskClass,
    TriageState,
    TriageUncertainty,
)
from victus_api.triage.service import _apply_gate


def _risk(next_action: str = "clinical_referral") -> PerDiseaseRisk:
    probs = {
        RiskClass.LOW_RISK: 0.1,
        RiskClass.ELEVATED_RISK: 0.2,
        RiskClass.HIGH_RISK: 0.3,
        RiskClass.VERY_HIGH_RISK: 0.4,
    }
    return PerDiseaseRisk(
        disease=Disease.DIABETES,
        state=TriageState.RED,
        top_class=RiskClass.VERY_HIGH_RISK,
        class_probabilities=probs,
        evidence={k: v * 10 for k, v in probs.items()},
        uncertainty=TriageUncertainty(
            vacuity=0.2, aleatoric=0.1, epistemic=0.1, strength=10.0
        ),
        contributing_factors=["waist-to-height 0.62"],
        next_action=next_action,
    )


# --- the gate condition ------------------------------------------------------


def test_default_settings_are_research_demonstrator() -> None:
    s = Settings()
    assert s.clinical_claims_active is False
    assert resolve_claims_mode(s) is ClaimsMode.RESEARCH_DEMONSTRATOR


def test_flag_alone_does_not_open_the_gate() -> None:
    # Enabling the flag without naming a validated model card is not enough.
    s = Settings(clinical_claims_enabled=True, clinical_claims_model_card=None)
    assert s.clinical_claims_active is False
    assert resolve_claims_mode(s) is ClaimsMode.RESEARCH_DEMONSTRATOR


def test_flag_plus_model_card_opens_the_gate() -> None:
    s = Settings(
        clinical_claims_enabled=True, clinical_claims_model_card="triage-mc-v1"
    )
    assert s.clinical_claims_active is True
    assert resolve_claims_mode(s) is ClaimsMode.CLINICAL


def test_model_card_without_flag_stays_closed() -> None:
    s = Settings(clinical_claims_enabled=False, clinical_claims_model_card="mc")
    assert s.clinical_claims_active is False


# --- the response transform --------------------------------------------------


def test_clinical_mode_passes_output_through_unchanged() -> None:
    authorised, disclaimer, next_action, pd = _apply_gate(
        mode=ClaimsMode.CLINICAL,
        safety_triggered=False,
        next_action="clinical_referral",
        per_disease=[_risk()],
    )
    assert authorised is True
    assert disclaimer == CLINICAL_DISCLAIMER
    assert next_action == "clinical_referral"
    assert pd[0].next_action == "clinical_referral"


def test_research_mode_declaims_the_actionable_directives() -> None:
    authorised, disclaimer, next_action, pd = _apply_gate(
        mode=ClaimsMode.RESEARCH_DEMONSTRATOR,
        safety_triggered=False,
        next_action="clinical_referral",
        per_disease=[_risk(), _risk(next_action="routine_followup")],
    )
    assert authorised is False
    assert disclaimer == RESEARCH_DISCLAIMER
    assert next_action == RESEARCH_NEXT_ACTION
    assert all(d.next_action == RESEARCH_PER_DISEASE_ACTION for d in pd)


def test_research_mode_preserves_emergency_safety_guidance() -> None:
    # A deterministic red-flag override is conservative first-aid, not a model
    # claim — its emergency directive survives even the closed gate.
    _, _, next_action, _ = _apply_gate(
        mode=ClaimsMode.RESEARCH_DEMONSTRATOR,
        safety_triggered=True,
        next_action="immediate_clinical_referral",
        per_disease=[_risk()],
    )
    assert next_action == "immediate_clinical_referral"
