"""Predictive-task contracts for the 3B-Triage model — the anti-leakage layer.

Each NCD label is defined by a specific measurement (the *ground truth*). If that
measurement — or a feature that deterministically encodes it — is also a model
*input*, the model merely re-derives the threshold and the reported performance is
circular. This module states, per disease, exactly which features a disease head
is allowed to see, and provides a mask the training loop and inference path apply
so a head can **never** consume its own defining measurement.

Task kinds
----------
* **DETERMINISTIC** — the label is a deterministic readout of measured inputs
  (obesity = BMI≥30). When all defining inputs are present the result should be
  reported as a *rule*, not an ML prediction. A model head is only meaningful as a
  proxy that excludes the defining inputs.
* **CONDITIONAL** — deterministic when the defining measurement is present
  (hypertension = BP≥140/90 with a cuff), a genuine proxy when it is absent
  (predict from anthropometry where no BP device exists).
* **PREDICTIVE** — a genuine proxy task; the defining marker is never a feature
  (diabetes = HbA1c/FPG, which the tape-measure feature vector does not contain).

The masks are aligned to :data:`victus_api.triage.features.FEATURE_NAMES`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from victus_api.triage.features import FEATURE_NAMES
from victus_api.triage.schemas import Disease


class TaskKind(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    CONDITIONAL = "CONDITIONAL"
    PREDICTIVE = "PREDICTIVE"


@dataclass(frozen=True, slots=True)
class PredictiveTask:
    disease: Disease
    kind: TaskKind
    # Plain-English statement of what defines the label (the ground truth).
    label_definition: str
    # Features that encode the defining measurement — forbidden as inputs to this
    # disease's head. Every entry must be a member of FEATURE_NAMES.
    forbidden_features: frozenset[str]
    rationale: str

    @property
    def allowed_features(self) -> tuple[str, ...]:
        return tuple(f for f in FEATURE_NAMES if f not in self.forbidden_features)


# Diabetes markers that must NEVER appear in the feature vector (asserted below).
DEFINING_MARKERS_NOT_FEATURES: frozenset[str] = frozenset(
    {"hba1c_percent", "fasting_glucose_mmol_l"}
)


PREDICTIVE_TASKS: dict[Disease, PredictiveTask] = {
    Disease.OBESITY: PredictiveTask(
        disease=Disease.OBESITY,
        kind=TaskKind.DETERMINISTIC,
        label_definition="BMI ≥ 30 kg/m² (WHO), computed from height + weight.",
        # BMI and its components fully determine the label; WHtR encodes height.
        forbidden_features=frozenset({"height_cm", "weight_kg", "bmi", "whtr"}),
        rationale=(
            "With height+weight measured, obesity is a deterministic readout — "
            "report the BMI rule. A head is only meaningful as a waist/whr-based "
            "proxy that excludes the BMI-defining inputs."
        ),
    ),
    Disease.HYPERTENSION: PredictiveTask(
        disease=Disease.HYPERTENSION,
        kind=TaskKind.CONDITIONAL,
        label_definition="BP ≥ 140/90 mmHg or on treatment.",
        # The cuff reading (and pulse pressure derived from it) defines the label.
        forbidden_features=frozenset(
            {"systolic_bp", "diastolic_bp", "bp_mask", "pulse_pressure"}
        ),
        rationale=(
            "When a cuff reading is present the label is deterministic; the head "
            "is a proxy for settings without a BP device, so it must not see the "
            "cuff reading."
        ),
    ),
    Disease.DIABETES: PredictiveTask(
        disease=Disease.DIABETES,
        kind=TaskKind.PREDICTIVE,
        label_definition="HbA1c ≥ 6.5 % or FPG ≥ 7.0 mmol/L (ADA), or on treatment.",
        # The blood markers are never in the tape-measure feature vector — this is
        # the genuine non-invasive prediction task.
        forbidden_features=frozenset(),
        rationale=(
            "The defining blood markers are not features, so anthropometry + "
            "symptoms → diabetes is a real proxy task with no leakage."
        ),
    ),
}


def _assert_contracts_consistent() -> None:
    feature_set = set(FEATURE_NAMES)
    for task in PREDICTIVE_TASKS.values():
        unknown = task.forbidden_features - feature_set
        if unknown:
            raise ValueError(
                f"{task.disease.value}: forbidden features not in FEATURE_NAMES: "
                f"{sorted(unknown)}"
            )
    # The diabetes ground-truth markers must not have leaked into the features.
    leaked = DEFINING_MARKERS_NOT_FEATURES & feature_set
    if leaked:
        raise ValueError(f"Defining markers leaked into FEATURE_NAMES: {sorted(leaked)}")


_assert_contracts_consistent()


def leakage_mask(disease: Disease) -> tuple[float, ...]:
    """1.0 for allowed features, 0.0 for the disease's forbidden features."""
    forbidden = PREDICTIVE_TASKS[disease].forbidden_features
    return tuple(0.0 if name in forbidden else 1.0 for name in FEATURE_NAMES)


def mask_vector(vector: list[float], disease: Disease) -> list[float]:
    """Zero out the forbidden features in a feature vector for ``disease``.

    The training loop applies this per-head so a disease never trains on its
    defining measurement; the inference path applies the same mask so train and
    serve agree.
    """
    if len(vector) != len(FEATURE_NAMES):
        raise ValueError(
            f"feature vector length {len(vector)} != {len(FEATURE_NAMES)}"
        )
    mask = leakage_mask(disease)
    return [v * m for v, m in zip(vector, mask, strict=True)]
