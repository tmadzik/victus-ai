"""Feature engineering for the EDL classifier.

We surface both the raw anthropometrics and a small set of clinically-meaningful
derived ratios. Missing optional inputs (hip circumference, BP) are encoded with
explicit ``mask`` channels so downstream models can learn to attend selectively
without imputation bias.
"""

from __future__ import annotations

from dataclasses import dataclass

from victus_api.triage.schemas import Sex, TapeMeasureInputs


@dataclass(frozen=True, slots=True)
class DerivedFeatures:
    bmi: float | None
    whtr: float | None
    whr: float | None
    pulse_pressure_mmhg: float | None


def compute_derived(inputs: TapeMeasureInputs) -> DerivedFeatures:
    bmi = inputs.weight_kg / ((inputs.height_cm / 100.0) ** 2)
    whtr = inputs.waist_cm / inputs.height_cm
    whr = inputs.waist_cm / inputs.hip_cm if inputs.hip_cm else None
    pulse_pressure = (
        inputs.systolic_bp_mmhg - inputs.diastolic_bp_mmhg
        if inputs.systolic_bp_mmhg is not None and inputs.diastolic_bp_mmhg is not None
        else None
    )
    return DerivedFeatures(
        bmi=round(bmi, 2),
        whtr=round(whtr, 4),
        whr=round(whr, 4) if whr is not None else None,
        pulse_pressure_mmhg=round(pulse_pressure, 2) if pulse_pressure is not None else None,
    )


# Feature ordering for both the rule-based and trained backends.
FEATURE_NAMES: tuple[str, ...] = (
    "height_cm",
    "weight_kg",
    "waist_cm",
    "age_years",
    "sex_male",
    "sex_female",
    "bmi",
    "whtr",
    "whr",
    "whr_mask",
    "systolic_bp",
    "diastolic_bp",
    "bp_mask",
    "pulse_pressure",
)


def to_feature_vector(
    inputs: TapeMeasureInputs,
    derived: DerivedFeatures,
) -> list[float]:
    """Build a deterministic feature vector aligned with ``FEATURE_NAMES``.

    Mask channels are 1.0 when the corresponding optional input is present
    and 0.0 otherwise; the masked value itself is 0.0 (additive identity) so
    a downstream linear layer can cleanly skip absent features.
    """
    sex_male = 1.0 if inputs.sex == Sex.MALE else 0.0
    sex_female = 1.0 if inputs.sex == Sex.FEMALE else 0.0

    whr_present = derived.whr is not None
    bp_present = (
        inputs.systolic_bp_mmhg is not None
        and inputs.diastolic_bp_mmhg is not None
    )

    return [
        float(inputs.height_cm),
        float(inputs.weight_kg),
        float(inputs.waist_cm),
        float(inputs.age_years),
        sex_male,
        sex_female,
        float(derived.bmi) if derived.bmi is not None else 0.0,
        float(derived.whtr) if derived.whtr is not None else 0.0,
        float(derived.whr) if whr_present and derived.whr is not None else 0.0,
        1.0 if whr_present else 0.0,
        (
            float(inputs.systolic_bp_mmhg)
            if bp_present and inputs.systolic_bp_mmhg is not None
            else 0.0
        ),
        (
            float(inputs.diastolic_bp_mmhg)
            if bp_present and inputs.diastolic_bp_mmhg is not None
            else 0.0
        ),
        1.0 if bp_present else 0.0,
        float(derived.pulse_pressure_mmhg)
        if derived.pulse_pressure_mmhg is not None
        else 0.0,
    ]
