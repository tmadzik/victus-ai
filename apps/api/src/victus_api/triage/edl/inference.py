"""Pluggable EDL inference backends.

Two backends behind a single :class:`EvidentialPredictor` protocol:

1. :class:`EvidentialTorchModel` — loads a serialized PyTorch checkpoint when
   ``VICTUS_TRIAGE_MODEL_PATH`` is set and points at a readable file. Lazy-
   imports ``torch`` so the API runtime stays slim until ML is needed.

2. :class:`RuleBasedEvidentialFallback` — clinically-grounded evidence
   synthesis using widely-published WHO / ISH / ADA thresholds. Produces the
   *same* Dirichlet output structure as the trained backend, so the state
   machine and UI work identically from day one and silently upgrade when a
   checkpoint is shipped.

The factory :func:`get_predictor` selects the best available backend and
caches the choice for the lifetime of the worker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from victus_api.core.logging import get_logger
from victus_api.triage.edl.dirichlet import (
    dirichlet_stats,
    epistemic_uncertainty,
    expected_dirichlet_entropy,
)
from victus_api.triage.features import (
    FEATURE_NAMES,
    DerivedFeatures,
    to_feature_vector,
)
from victus_api.triage.schemas import RISK_CLASSES, RiskClass, TapeMeasureInputs

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EvidentialPrediction:
    evidence: dict[RiskClass, float]
    alpha: dict[RiskClass, float]
    expected_probs: dict[RiskClass, float]
    strength: float
    vacuity: float
    aleatoric: float
    epistemic: float
    top_class: RiskClass
    model_kind: str
    model_version: str


class EvidentialPredictor(Protocol):
    model_kind: str
    model_version: str

    def predict(
        self, inputs: TapeMeasureInputs, derived: DerivedFeatures
    ) -> EvidentialPrediction: ...


def finalize_prediction(
    evidence: list[float], *, model_kind: str, model_version: str
) -> EvidentialPrediction:
    alpha, strength, expected, vacuity = dirichlet_stats(evidence)
    aleatoric = expected_dirichlet_entropy(alpha, strength)
    epistemic = epistemic_uncertainty(alpha, strength, aleatoric=aleatoric)
    top_idx = max(range(len(expected)), key=expected.__getitem__)
    top_class = RISK_CLASSES[top_idx]
    return EvidentialPrediction(
        evidence={cls: float(e) for cls, e in zip(RISK_CLASSES, evidence, strict=True)},
        alpha={cls: float(a) for cls, a in zip(RISK_CLASSES, alpha, strict=True)},
        expected_probs={cls: float(p) for cls, p in zip(RISK_CLASSES, expected, strict=True)},
        strength=float(strength),
        vacuity=float(vacuity),
        aleatoric=float(aleatoric),
        epistemic=float(epistemic),
        top_class=top_class,
        model_kind=model_kind,
        model_version=model_version,
    )


# ---------------------------------------------------------------------------
# Trained backend
# ---------------------------------------------------------------------------


class EvidentialTorchModel:
    """Loads a trained PyTorch evidential classifier from disk.

    Expected on-disk layout::

        <checkpoint>.pt            # state_dict written via ``torch.save``
        <checkpoint>.pt.meta.json  # {
                                   #   "feature_names": [...],
                                   #   "label_mapping": ["LOW_RISK", ...],
                                   #   "hidden_dims": [64, 32],
                                   #   "scaler": {"mean": [...], "std": [...]},
                                   #   "version": "...",
                                   #   "training_metrics": {...}  # optional
                                   # }

    The sidecar pins the *exact* feature ordering and standardization
    parameters used at training time so inference applies the same transform.
    A mismatch (different feature names, missing scaler, wrong dimensions)
    raises at construction time — we refuse to silently mis-serve inference.
    """

    model_kind: str = "trained_torch_v1"

    def __init__(self, checkpoint_path: Path) -> None:
        import json

        import torch

        from victus_api.triage.edl.dirichlet import (
            build_dann_evidential_model,
            build_evidential_mlp,
        )

        meta_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".meta.json")
        if not meta_path.exists():
            raise FileNotFoundError(
                f"Checkpoint meta sidecar not found at {meta_path}; refusing to load."
            )
        meta = json.loads(meta_path.read_text())
        if tuple(meta["feature_names"]) != FEATURE_NAMES:
            raise ValueError(
                "Checkpoint feature ordering does not match "
                "victus_api.triage.features.FEATURE_NAMES",
            )
        label_mapping = tuple(meta.get("label_mapping", []))
        expected_labels = tuple(cls.value for cls in RISK_CLASSES)
        if label_mapping != expected_labels:
            raise ValueError(
                "Checkpoint label_mapping does not match RISK_CLASSES; "
                f"expected {expected_labels}, got {label_mapping}",
            )
        self.model_version = str(meta.get("version", "unknown"))

        scaler = meta.get("scaler")
        if scaler is None:
            raise ValueError(
                "Checkpoint meta is missing 'scaler' (mean/std). Standardization "
                "must be persisted to keep training and inference in lockstep.",
            )
        if len(scaler["mean"]) != len(FEATURE_NAMES) or len(scaler["std"]) != len(FEATURE_NAMES):
            raise ValueError("Scaler mean/std length does not match feature count.")

        self._torch = torch
        self._device = torch.device("cpu")
        self._scaler_mean = torch.tensor(scaler["mean"], dtype=torch.float32)
        self._scaler_std = torch.tensor(scaler["std"], dtype=torch.float32).clamp(min=1e-6)

        hidden_dims = tuple(int(h) for h in meta.get("hidden_dims", (64, 32)))
        architecture = str(meta.get("architecture", "sequential_v1"))

        if architecture == "sequential_v1":
            self._model = build_evidential_mlp(
                input_dim=len(FEATURE_NAMES),
                num_classes=len(RISK_CLASSES),
                hidden_dims=hidden_dims,
                dropout=0.0,
            )
            self._forward = self._forward_sequential
            self.model_kind = "trained_torch_v1"
            num_domains: int | None = None
        elif architecture == "dann_v1":
            domain_mapping = tuple(meta.get("domain_mapping", ()))
            if not domain_mapping:
                raise ValueError("dann_v1 checkpoint missing 'domain_mapping'")
            num_domains = len(domain_mapping)
            domain_hidden = int(meta.get("domain_hidden", 32))
            self._model = build_dann_evidential_model(
                input_dim=len(FEATURE_NAMES),
                num_classes=len(RISK_CLASSES),
                num_domains=num_domains,
                hidden_dims=hidden_dims,
                domain_hidden=domain_hidden,
                dropout=0.0,
            )
            self._forward = self._forward_dann
            self.model_kind = "trained_torch_dann_v1"
        else:
            raise ValueError(
                f"Unknown architecture {architecture!r}; expected "
                "'sequential_v1' or 'dann_v1'."
            )

        state_dict = torch.load(checkpoint_path, map_location=self._device, weights_only=True)
        self._model.load_state_dict(state_dict)
        self._model.eval()
        log.info(
            "edl_torch_model_loaded",
            path=str(checkpoint_path),
            version=self.model_version,
            architecture=architecture,
            hidden_dims=list(hidden_dims),
            num_domains=num_domains,
        )

    def _forward_sequential(self, x: Any) -> Any:
        return self._model(x)

    def _forward_dann(self, x: Any) -> Any:
        # Inference path skips the domain head entirely.
        return self._model.predict_evidence(x)

    def predict(
        self, inputs: TapeMeasureInputs, derived: DerivedFeatures
    ) -> EvidentialPrediction:
        torch = self._torch
        features = to_feature_vector(inputs, derived)
        with torch.no_grad():
            x = torch.tensor([features], dtype=torch.float32, device=self._device)
            x = (x - self._scaler_mean) / self._scaler_std
            evidence_tensor = self._forward(x)[0]
        evidence = [float(e) for e in evidence_tensor.tolist()]
        return finalize_prediction(
            evidence,
            model_kind=self.model_kind,
            model_version=self.model_version,
        )


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _RuleEvidence:
    target: RiskClass
    weight: float
    reason: str


def _bmi_evidence(bmi: float | None) -> list[_RuleEvidence]:
    if bmi is None:
        return []
    # WHO BMI categories. Weights chosen so a single signal alone does not
    # dominate the vacuity prior; multiple signals compound into RED.
    if bmi >= 40.0:
        return [_RuleEvidence(RiskClass.VERY_HIGH_RISK, 4.0, "BMI ≥ 40 (Obesity III)")]
    if bmi >= 35.0:
        return [_RuleEvidence(RiskClass.HIGH_RISK, 3.0, "BMI ≥ 35 (Obesity II)")]
    if bmi >= 30.0:
        return [_RuleEvidence(RiskClass.HIGH_RISK, 2.0, "BMI ≥ 30 (Obesity I)")]
    if bmi >= 25.0:
        return [_RuleEvidence(RiskClass.ELEVATED_RISK, 1.5, "BMI ≥ 25 (Overweight)")]
    if bmi >= 18.5:
        return [_RuleEvidence(RiskClass.LOW_RISK, 2.0, "BMI in healthy range")]
    return [_RuleEvidence(RiskClass.ELEVATED_RISK, 1.0, "BMI < 18.5 (Underweight)")]


def _whtr_evidence(whtr: float | None) -> list[_RuleEvidence]:
    if whtr is None:
        return []
    # Ashwell boundary: WHtR ≥ 0.5 is a cardiometabolic risk signal.
    if whtr >= 0.6:
        return [_RuleEvidence(RiskClass.HIGH_RISK, 2.5, "WHtR ≥ 0.6 (severe central adiposity)")]
    if whtr >= 0.5:
        return [_RuleEvidence(RiskClass.ELEVATED_RISK, 1.5, "WHtR ≥ 0.5 (central adiposity)")]
    return [_RuleEvidence(RiskClass.LOW_RISK, 1.0, "WHtR < 0.5")]


def _bp_evidence(systolic: float | None, diastolic: float | None) -> list[_RuleEvidence]:
    if systolic is None or diastolic is None:
        return []
    # ACC/AHA + WHO/ISH categories.
    if systolic >= 180.0 or diastolic >= 120.0:
        return [
            _RuleEvidence(RiskClass.VERY_HIGH_RISK, 5.0, "Hypertensive crisis (≥180/120)")
        ]
    if systolic >= 140.0 or diastolic >= 90.0:
        return [_RuleEvidence(RiskClass.HIGH_RISK, 3.0, "Stage 2 hypertension (≥140/90)")]
    if systolic >= 130.0 or diastolic >= 80.0:
        return [_RuleEvidence(RiskClass.ELEVATED_RISK, 1.5, "Stage 1 hypertension (≥130/80)")]
    if systolic >= 120.0:
        return [_RuleEvidence(RiskClass.ELEVATED_RISK, 0.5, "Elevated BP (≥120 systolic)")]
    return [_RuleEvidence(RiskClass.LOW_RISK, 1.0, "BP < 120/80")]


def _age_evidence(age: int) -> list[_RuleEvidence]:
    if age >= 65:
        return [_RuleEvidence(RiskClass.ELEVATED_RISK, 1.0, "Age ≥ 65")]
    if age >= 45:
        return [_RuleEvidence(RiskClass.ELEVATED_RISK, 0.5, "Age ≥ 45")]
    return []


class RuleBasedEvidentialFallback:
    """Clinically-grounded evidence synthesis when no checkpoint is available.

    The evidence is intentionally damped (small magnitudes, single-digit total)
    so vacuity ``u = K/S`` stays meaningfully > 0 — the API reports the result
    with appropriate uncertainty rather than impersonating a confident trained
    model. Plausibility flags additionally push the state machine to YELLOW.
    """

    model_kind: str = "rule_based_fallback_v1"
    model_version: str = "1.0.0"

    def predict(
        self, inputs: TapeMeasureInputs, derived: DerivedFeatures
    ) -> EvidentialPrediction:
        evidence_per_class: dict[RiskClass, float] = dict.fromkeys(RISK_CLASSES, 0.0)

        all_signals: list[_RuleEvidence] = []
        all_signals.extend(_bmi_evidence(derived.bmi))
        all_signals.extend(_whtr_evidence(derived.whtr))
        all_signals.extend(
            _bp_evidence(inputs.systolic_bp_mmhg, inputs.diastolic_bp_mmhg)
        )
        all_signals.extend(_age_evidence(inputs.age_years))

        for signal in all_signals:
            evidence_per_class[signal.target] += signal.weight

        evidence_vec = [evidence_per_class[cls] for cls in RISK_CLASSES]
        return finalize_prediction(
            evidence_vec,
            model_kind=self.model_kind,
            model_version=self.model_version,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_predictor() -> EvidentialPredictor:
    path_str = os.environ.get("VICTUS_TRIAGE_MODEL_PATH")
    if path_str:
        path = Path(path_str)
        if path.is_file():
            try:
                return EvidentialTorchModel(path)
            except Exception:
                log.exception(
                    "edl_torch_model_load_failed",
                    path=str(path),
                    fallback=RuleBasedEvidentialFallback.model_kind,
                )
        else:
            log.warning(
                "edl_torch_model_path_missing",
                path=str(path),
                fallback=RuleBasedEvidentialFallback.model_kind,
            )
    log.info("edl_predictor_selected", kind=RuleBasedEvidentialFallback.model_kind)
    return RuleBasedEvidentialFallback()
