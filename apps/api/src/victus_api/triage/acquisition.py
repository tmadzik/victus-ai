"""Active-learning ground-truth acquisition — rank assessments by how much a
confirmatory lab test would improve the model, using the EDL uncertainty the
triage pipeline already produces.

Why this exists: prospective validation (docs/PROSPECTIVE_VALIDATION_PLAN.md)
needs confirmed labels, and confirmatory glycaemia testing is the scarce, costly
resource. Rather than test a random sample, spend those tests where they are most
informative — where the model is epistemically uncertain AND sitting near a
decision boundary. That is classic uncertainty × boundary active learning, and it
can make the validation study several-fold more sample-efficient.

Scope: acquisition targets the **diabetes** head. Obesity (BMI≥30) and
hypertension (BP≥140/90) are *deterministic functions of a measured input* — a
tape measure or a cuff confirms them, not a lab — so they are not the bottleneck
this rations. Diabetes (HbA1c/FPG-confirmed) is the genuine predictive task, per
the leakage-guarded task definitions (triage/tasks.py).

Pure module: no I/O, no DB. The research service applies it over stored
assessments to build the coordinator worklist.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from victus_api.triage.schemas import Disease, PerDiseaseRisk, RiskClass

# Acquisition score = a convex blend of two signals, each in [0, 1]:
#   * epistemic uncertainty (vacuity — the Dirichlet "I don't know" mass), and
#   * decision-boundary proximity (how close the top-two class probabilities are).
# Equal weight by default; both matter and neither should dominate.
WEIGHT_EPISTEMIC = 0.5
WEIGHT_BOUNDARY = 0.5

# Priority-band thresholds on the [0, 1] acquisition score.
PRIORITY_HIGH_MIN = 0.66
PRIORITY_MEDIUM_MIN = 0.40

# The confirmatory reference standard per disease (STARD reference for the
# validation study). Only the lab-confirmed set is rationed by acquisition.
CONFIRMATORY_TEST: dict[Disease, str] = {
    Disease.DIABETES: "HbA1c or fasting plasma glucose",
    Disease.HYPERTENSION: "standardized cuff blood pressure",
    Disease.OBESITY: "measured BMI",
}
# Diseases whose ground truth needs a lab (the scarce resource). Obesity and
# hypertension are deterministic from a measured input, so they are excluded.
LAB_CONFIRMED_DISEASES: frozenset[Disease] = frozenset({Disease.DIABETES})


class AcquisitionPriority(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class AcquisitionScore:
    """How valuable acquiring confirmatory ground truth for this assessment is."""

    acquisition_score: float
    priority: AcquisitionPriority
    driving_disease: Disease
    confirmatory_test: str
    epistemic_component: float
    boundary_component: float
    rationale: str


def _boundary_proximity(class_probabilities: dict[RiskClass, float]) -> float:
    """1 − (p_top − p_second), clamped to [0, 1]. High when the top two classes
    are close, i.e. the case sits on a decision boundary where a confirmed label
    most sharpens the operating threshold."""
    probs = sorted(class_probabilities.values(), reverse=True)
    if len(probs) < 2:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (probs[0] - probs[1])))


def _priority(score: float) -> AcquisitionPriority:
    if score >= PRIORITY_HIGH_MIN:
        return AcquisitionPriority.HIGH
    if score >= PRIORITY_MEDIUM_MIN:
        return AcquisitionPriority.MEDIUM
    return AcquisitionPriority.LOW


def score_assessment(per_disease: list[PerDiseaseRisk]) -> AcquisitionScore | None:
    """Acquisition value for one assessment, driven by the lab-confirmed head(s).

    Returns ``None`` when no lab-confirmed disease is present (nothing to ration).
    """
    candidates = [r for r in per_disease if r.disease in LAB_CONFIRMED_DISEASES]
    if not candidates:
        return None

    best: AcquisitionScore | None = None
    for risk in candidates:
        epistemic = max(0.0, min(1.0, risk.uncertainty.vacuity))
        boundary = _boundary_proximity(risk.class_probabilities)
        score = WEIGHT_EPISTEMIC * epistemic + WEIGHT_BOUNDARY * boundary
        if best is None or score > best.acquisition_score:
            test = CONFIRMATORY_TEST[risk.disease]
            best = AcquisitionScore(
                acquisition_score=round(score, 4),
                priority=_priority(score),
                driving_disease=risk.disease,
                confirmatory_test=test,
                epistemic_component=round(epistemic, 4),
                boundary_component=round(boundary, 4),
                rationale=(
                    f"{risk.disease.value.title()}: epistemic uncertainty "
                    f"(vacuity {epistemic:.2f}) with a narrow class margin "
                    f"(boundary {boundary:.2f}). A confirmatory {test} would be "
                    f"high-value for validating and calibrating this head."
                ),
            )
    return best
