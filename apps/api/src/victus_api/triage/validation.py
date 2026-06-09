"""Cross-field plausibility checks for Pathway A inputs.

Each detected anomaly raises a :class:`PlausibilityFlag` rather than rejecting
the payload — the assessment still runs but the state machine pushes results
into YELLOW when any plausibility issue surfaces. This keeps the field-collector
workflow (community health workers using tape measures) resilient to common
unit-confusion errors instead of failing closed.

Rules implemented:

* ``WAIST_GT_HEIGHT`` — physically impossible.
* ``WAIST_TOO_SMALL`` — WHtR < 0.30 (implausible even for paediatric patients).
* ``BP_INVERTED`` — systolic ≤ diastolic.
* ``BP_EXTREME`` — systolic > 220 or diastolic > 140 (hypertensive crisis;
  state machine flags but RED is still appropriate clinically).
* ``BMI_OUT_OF_RANGE`` — BMI < 10 or > 70 (clinical extremes that almost
  always indicate a data-entry error).
* ``POSSIBLE_UNIT_CONFUSION_HEIGHT`` — height < 100 cm in adults (likely
  metres entered as centimetres).
* ``POSSIBLE_UNIT_CONFUSION_WEIGHT`` — weight > 250 kg AND age > 12 (likely
  pounds entered as kilograms).
"""

from __future__ import annotations

from victus_api.triage.schemas import PlausibilityFlag, TapeMeasureInputs


def detect_plausibility_flags(inputs: TapeMeasureInputs) -> list[PlausibilityFlag]:
    flags: list[PlausibilityFlag] = []

    bmi = inputs.weight_kg / ((inputs.height_cm / 100.0) ** 2)
    whtr = inputs.waist_cm / inputs.height_cm

    if inputs.waist_cm >= inputs.height_cm:
        flags.append(PlausibilityFlag.WAIST_GT_HEIGHT)
    if whtr < 0.30:
        flags.append(PlausibilityFlag.WAIST_TOO_SMALL)
    if bmi < 10.0 or bmi > 70.0:
        flags.append(PlausibilityFlag.BMI_OUT_OF_RANGE)

    if inputs.age_years >= 13 and inputs.height_cm < 100.0:
        flags.append(PlausibilityFlag.POSSIBLE_UNIT_CONFUSION_HEIGHT)
    if inputs.age_years >= 13 and inputs.weight_kg > 250.0:
        flags.append(PlausibilityFlag.POSSIBLE_UNIT_CONFUSION_WEIGHT)

    systolic = inputs.systolic_bp_mmhg
    diastolic = inputs.diastolic_bp_mmhg
    if systolic is not None and diastolic is not None:
        if systolic <= diastolic:
            flags.append(PlausibilityFlag.BP_INVERTED)
        if systolic > 220.0 or diastolic > 140.0:
            flags.append(PlausibilityFlag.BP_EXTREME)

    return flags
