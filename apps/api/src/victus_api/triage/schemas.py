"""Pydantic v2 DTOs for the 3B-Triage domain.

Field-level constraints reject zero/negative anthropometrics and bound
plausible physiological ranges. Cross-field plausibility (e.g. waist > height,
inverted BP) is checked in ``validation.py`` because we still want to ingest
those payloads — they become YELLOW outputs with explicit plausibility flags
rather than 422 rejections.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# --- Enums kept in sync with packages/contracts and db.models -----------------


class Sex(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class RiskClass(str, enum.Enum):
    LOW_RISK = "LOW_RISK"
    ELEVATED_RISK = "ELEVATED_RISK"
    HIGH_RISK = "HIGH_RISK"
    VERY_HIGH_RISK = "VERY_HIGH_RISK"


RISK_CLASSES: tuple[RiskClass, ...] = (
    RiskClass.LOW_RISK,
    RiskClass.ELEVATED_RISK,
    RiskClass.HIGH_RISK,
    RiskClass.VERY_HIGH_RISK,
)


class Disease(str, enum.Enum):
    """The three NCDs screened by Pathway A, each weighted independently."""

    OBESITY = "OBESITY"
    HYPERTENSION = "HYPERTENSION"
    DIABETES = "DIABETES"


# Fixed order — used for the model's per-disease heads and the UI layout.
DISEASES: tuple[Disease, ...] = (
    Disease.OBESITY,
    Disease.HYPERTENSION,
    Disease.DIABETES,
)


class TriageState(str, enum.Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


SAFETY_OVERRIDE_SYMPTOM_KEYS: frozenset[str] = frozenset(
    {
        "polydipsia_unquenchable_thirst",
        "blurred_vision_progressive",
        "non_healing_foot_sore",
        "chest_pain_radiating",
        "severe_headache_with_visual_change",
        "polyuria_nocturia_severe",
        "unexplained_weight_loss_recent",
    }
)

# Which disease a red-flag symptom escalates to RED (in addition to forcing the
# overall state to RED). Drives per-disease referral on safety override.
SAFETY_OVERRIDE_DISEASE: dict[str, Disease] = {
    "polydipsia_unquenchable_thirst": Disease.DIABETES,
    "polyuria_nocturia_severe": Disease.DIABETES,
    "non_healing_foot_sore": Disease.DIABETES,
    "unexplained_weight_loss_recent": Disease.DIABETES,
    "blurred_vision_progressive": Disease.DIABETES,
    "chest_pain_radiating": Disease.HYPERTENSION,
    "severe_headache_with_visual_change": Disease.HYPERTENSION,
}

CONTEXTUAL_SYMPTOM_KEYS: frozenset[str] = frozenset(
    {
        "fatigue_persistent",
        "family_history_diabetes",
        "family_history_hypertension",
        "smoker_current",
        "physical_activity_low",
    }
)


class PlausibilityFlag(str, enum.Enum):
    BMI_OUT_OF_RANGE = "BMI_OUT_OF_RANGE"
    WAIST_GT_HEIGHT = "WAIST_GT_HEIGHT"
    WAIST_TOO_SMALL = "WAIST_TOO_SMALL"
    BP_INVERTED = "BP_INVERTED"
    BP_EXTREME = "BP_EXTREME"
    POSSIBLE_UNIT_CONFUSION_HEIGHT = "POSSIBLE_UNIT_CONFUSION_HEIGHT"
    POSSIBLE_UNIT_CONFUSION_WEIGHT = "POSSIBLE_UNIT_CONFUSION_WEIGHT"


# --- Inputs ------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


Positive = Annotated[float, Field(gt=0)]


class TapeMeasureInputs(_Base):
    height_cm: Annotated[float, Field(gt=0, ge=50, le=250)]
    weight_kg: Annotated[float, Field(gt=0, ge=5, le=400)]
    waist_cm: Annotated[float, Field(gt=0, ge=30, le=250)]
    hip_cm: Annotated[float, Field(gt=0, ge=40, le=250)] | None = None
    age_years: Annotated[int, Field(gt=0, ge=1, le=120)]
    sex: Sex
    systolic_bp_mmhg: Annotated[float, Field(gt=0, ge=50, le=260)] | None = None
    diastolic_bp_mmhg: Annotated[float, Field(gt=0, ge=30, le=160)] | None = None


class SymptomAudit(_Base):
    safety_triggers: list[str] = Field(default_factory=list, max_length=20)
    contextual: list[str] = Field(default_factory=list, max_length=20)


class TriageAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: TapeMeasureInputs
    symptoms: SymptomAudit


# --- Outputs -----------------------------------------------------------------


class DerivedFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bmi: float | None
    whtr: float | None
    whr: float | None
    pulse_pressure_mmhg: float | None


class TriageUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vacuity: Annotated[float, Field(ge=0.0, le=1.0)]
    aleatoric: Annotated[float, Field(ge=0.0)]
    epistemic: Annotated[float, Field(ge=0.0)]
    strength: Annotated[float, Field(gt=0.0)]


class PerDiseaseRisk(BaseModel):
    """Independent evidential risk assessment for a single NCD."""

    model_config = ConfigDict(extra="forbid")

    disease: Disease
    state: TriageState
    top_class: RiskClass
    class_probabilities: dict[RiskClass, float]
    evidence: dict[RiskClass, float]
    uncertainty: TriageUncertainty
    contributing_factors: list[str]
    next_action: str


class TriageAssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    overall_state: TriageState
    per_disease: list[PerDiseaseRisk]
    derived_features: DerivedFeatures
    plausibility_flags: list[PlausibilityFlag]
    safety_override_triggered: bool
    override_reasons: list[str]
    model_kind: str
    next_action: str
    created_at: datetime
