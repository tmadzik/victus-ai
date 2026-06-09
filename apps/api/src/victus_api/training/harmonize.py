"""Unified record schema + risk-class derivation per data source.

Every input dataset goes through a per-source loader (``datasets.py``) and
emits a list of :class:`HarmonizedRecord` objects. This module defines that
record + the clinical rules used to derive the four risk classes from each
source's native label and physiology.

Risk class derivation rules
---------------------------

**Pima diabetes** — ``Outcome=0 AND Glucose<100 AND BMI<25`` → LOW;
``Outcome=1 AND Glucose>200`` → VERY_HIGH; ``Outcome=1`` → HIGH;
otherwise ELEVATED.

**Body fat** — male-only cohort; American Council on Exercise body-fat bands.
``<20%`` → LOW, ``20–25%`` → ELEVATED, ``25–32%`` → HIGH, ``>32%`` → VERY_HIGH.

**UCI heart disease** — ``target=0 AND chol<200 AND trestbps<130 AND fbs=0``
→ LOW; ``target=0`` → ELEVATED; ``target=1`` → HIGH; ``target≥2`` → VERY_HIGH.

**Stroke** — ``stroke=1`` → VERY_HIGH; ``(hypertension OR heart_disease)
AND bmi>30`` → HIGH; ``hypertension OR heart_disease`` → ELEVATED; else LOW.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from victus_api.triage.features import FEATURE_NAMES
from victus_api.triage.schemas import RISK_CLASSES, RiskClass


class Domain(str, enum.Enum):
    """Measurement-provenance domains used by the DANN adversary.

    The label captures *measurement quality of the features the model sees*,
    not the originating study. Bodyfat and UCI heart are CLINICAL_GRADE
    because their dominant signal (true anthropometrics or measured trestbps)
    came from clinical instruments. Pima diabetes and the stroke cohort are
    SYNTHETIC because their anthropometrics were generated from priors.
    CHW_TAPE_MEASURE is constructed at training time by injecting realistic
    field-collection noise into CLINICAL_GRADE samples (see
    ``training.datasets.synthesize_chw_domain``).
    """

    CLINICAL_GRADE = "CLINICAL_GRADE"
    CHW_TAPE_MEASURE = "CHW_TAPE_MEASURE"
    SYNTHETIC = "SYNTHETIC"


DOMAINS: tuple[Domain, ...] = (
    Domain.CLINICAL_GRADE,
    Domain.CHW_TAPE_MEASURE,
    Domain.SYNTHETIC,
)
DOMAIN_INDEX: dict[Domain, int] = {d: i for i, d in enumerate(DOMAINS)}


@dataclass(frozen=True, slots=True)
class HarmonizedRecord:
    source: str
    domain: Domain
    height_cm: float
    weight_kg: float
    waist_cm: float
    hip_cm: float | None
    age_years: int
    sex: str  # "MALE" | "FEMALE" | "OTHER"
    systolic_bp_mmhg: float | None
    diastolic_bp_mmhg: float | None
    risk_class: RiskClass

    def derived(self) -> tuple[float, float, float | None, float | None]:
        bmi = self.weight_kg / ((self.height_cm / 100.0) ** 2)
        whtr = self.waist_cm / self.height_cm
        whr = (self.waist_cm / self.hip_cm) if self.hip_cm else None
        pulse = (
            self.systolic_bp_mmhg - self.diastolic_bp_mmhg
            if self.systolic_bp_mmhg is not None and self.diastolic_bp_mmhg is not None
            else None
        )
        return bmi, whtr, whr, pulse

    def feature_vector(self) -> list[float]:
        bmi, whtr, whr, pulse = self.derived()
        sex_male = 1.0 if self.sex == "MALE" else 0.0
        sex_female = 1.0 if self.sex == "FEMALE" else 0.0
        whr_present = whr is not None
        bp_present = (
            self.systolic_bp_mmhg is not None and self.diastolic_bp_mmhg is not None
        )
        return [
            float(self.height_cm),
            float(self.weight_kg),
            float(self.waist_cm),
            float(self.age_years),
            sex_male,
            sex_female,
            float(bmi),
            float(whtr),
            float(whr) if whr_present and whr is not None else 0.0,
            1.0 if whr_present else 0.0,
            (
                float(self.systolic_bp_mmhg)
                if bp_present and self.systolic_bp_mmhg is not None
                else 0.0
            ),
            float(self.diastolic_bp_mmhg)
            if bp_present and self.diastolic_bp_mmhg is not None
            else 0.0,
            1.0 if bp_present else 0.0,
            float(pulse) if pulse is not None else 0.0,
        ]


assert len(FEATURE_NAMES) == 14, (
    "HarmonizedRecord.feature_vector() is hard-coded to 14 features; "
    "if FEATURE_NAMES changes, update this method."
)


# --- Risk-class derivation rules ---------------------------------------------


def diabetes_risk_class(
    outcome: int, glucose: float, bmi: float
) -> RiskClass:
    if outcome == 1 and glucose > 200.0:
        return RiskClass.VERY_HIGH_RISK
    if outcome == 1:
        return RiskClass.HIGH_RISK
    if outcome == 0 and glucose < 100.0 and bmi < 25.0:
        return RiskClass.LOW_RISK
    return RiskClass.ELEVATED_RISK


def bodyfat_risk_class(body_fat_pct: float) -> RiskClass:
    # ACE male body-fat bands (cohort is all-male).
    if body_fat_pct > 32.0:
        return RiskClass.VERY_HIGH_RISK
    if body_fat_pct > 25.0:
        return RiskClass.HIGH_RISK
    if body_fat_pct > 20.0:
        return RiskClass.ELEVATED_RISK
    return RiskClass.LOW_RISK


def heart_risk_class(
    target: int,
    *,
    trestbps: float | None,
    chol: float | None,
    fbs: int | None,
) -> RiskClass:
    if target >= 2:
        return RiskClass.VERY_HIGH_RISK
    if target == 1:
        return RiskClass.HIGH_RISK
    healthy_bp = trestbps is None or trestbps < 130.0
    healthy_chol = chol is None or chol < 200.0
    healthy_fbs = fbs is None or fbs == 0
    if healthy_bp and healthy_chol and healthy_fbs:
        return RiskClass.LOW_RISK
    return RiskClass.ELEVATED_RISK


def stroke_risk_class(
    stroke: int, hypertension: int, heart_disease: int, bmi: float | None
) -> RiskClass:
    if stroke == 1:
        return RiskClass.VERY_HIGH_RISK
    risk_factor = hypertension == 1 or heart_disease == 1
    if risk_factor and bmi is not None and bmi > 30.0:
        return RiskClass.HIGH_RISK
    if risk_factor:
        return RiskClass.ELEVATED_RISK
    return RiskClass.LOW_RISK


CLASS_INDEX: dict[RiskClass, int] = {cls: i for i, cls in enumerate(RISK_CLASSES)}
