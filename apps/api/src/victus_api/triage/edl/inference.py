"""Pluggable EDL inference backends — per-disease evidential risk.

Pathway A weights three NCDs **independently**: obesity, hypertension and
diabetes each get their own Dirichlet over the four ``RiskClass`` tiers, their
own uncertainty decomposition, and (downstream) their own GREEN/YELLOW/RED
state. There is no single global risk class.

Two backends sit behind one :class:`EvidentialPredictor` protocol:

1. :class:`EvidentialTorchModel` — loads a serialized multi-head PyTorch
   checkpoint when ``VICTUS_TRIAGE_MODEL_PATH`` is set. Each disease has a
   dedicated evidential head over the shared, domain-invariant feature
   extractor. Lazy-imports ``torch`` so the API runtime stays slim.

2. :class:`RuleBasedEvidentialFallback` — clinically-grounded per-disease
   evidence synthesis using widely-published WHO / ISH / ADA / Ashwell
   thresholds. Produces the *same* per-disease Dirichlet structure as the
   trained backend, so the state machine and UI work identically from day one
   and silently upgrade when a checkpoint is shipped.

Contextual symptoms (family history, smoking, low activity) are not part of the
learned anthropometric model; they are applied as small additive rule evidence
on top of *either* backend, routed to the disease(s) they bear on. This keeps
both backends consistent and lets the network specialise on measurements.

The factory :func:`get_predictor` selects the best available backend and caches
the choice for the lifetime of the worker.
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
from victus_api.triage.schemas import (
    DISEASES,
    RISK_CLASSES,
    Disease,
    RiskClass,
    TapeMeasureInputs,
)

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EvidentialPrediction:
    """Finalized Dirichlet statistics for a single disease."""

    evidence: dict[RiskClass, float]
    alpha: dict[RiskClass, float]
    expected_probs: dict[RiskClass, float]
    strength: float
    vacuity: float
    aleatoric: float
    epistemic: float
    top_class: RiskClass


@dataclass(frozen=True, slots=True)
class MultiDiseasePrediction:
    """Per-disease evidential predictions plus their human-readable drivers."""

    per_disease: dict[Disease, EvidentialPrediction]
    contributing_factors: dict[Disease, list[str]]
    model_kind: str
    model_version: str


class EvidentialPredictor(Protocol):
    model_kind: str
    model_version: str

    def predict(
        self,
        inputs: TapeMeasureInputs,
        derived: DerivedFeatures,
        contextual_symptoms: frozenset[str],
    ) -> MultiDiseasePrediction: ...


def finalize_prediction(evidence: list[float]) -> EvidentialPrediction:
    """Turn a raw per-class evidence vector into a Dirichlet prediction.

    K-agnostic: the same routine serves the obesity, hypertension and diabetes
    heads. ``alpha = evidence + 1``, ``strength = sum(alpha)``, vacuity
    ``u = K / strength``; aleatoric is the expected Dirichlet entropy and
    epistemic the mutual-information (BALD) residual.
    """

    alpha, strength, expected, vacuity = dirichlet_stats(evidence)
    aleatoric = expected_dirichlet_entropy(alpha, strength)
    epistemic = epistemic_uncertainty(alpha, strength, aleatoric=aleatoric)
    top_idx = max(range(len(expected)), key=expected.__getitem__)
    top_class = RISK_CLASSES[top_idx]
    return EvidentialPrediction(
        evidence={cls: float(e) for cls, e in zip(RISK_CLASSES, evidence, strict=True)},
        alpha={cls: float(a) for cls, a in zip(RISK_CLASSES, alpha, strict=True)},
        expected_probs={
            cls: float(p) for cls, p in zip(RISK_CLASSES, expected, strict=True)
        },
        strength=float(strength),
        vacuity=float(vacuity),
        aleatoric=float(aleatoric),
        epistemic=float(epistemic),
        top_class=top_class,
    )


# ---------------------------------------------------------------------------
# Clinical evidence routing (shared by both backends)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Signal:
    target: RiskClass
    weight: float
    reason: str


def _empty_signals() -> dict[Disease, list[_Signal]]:
    return {disease: [] for disease in DISEASES}


def _obesity_signals(bmi: float | None, whtr: float | None) -> list[_Signal]:
    """Obesity is directly measurable from anthropometry (BMI primary)."""
    signals: list[_Signal] = []
    if bmi is not None:
        if bmi >= 40.0:
            signals.append(_Signal(RiskClass.VERY_HIGH_RISK, 4.0, "BMI ≥ 40 (obesity class III)"))
        elif bmi >= 35.0:
            signals.append(_Signal(RiskClass.HIGH_RISK, 3.0, "BMI ≥ 35 (obesity class II)"))
        elif bmi >= 30.0:
            signals.append(_Signal(RiskClass.HIGH_RISK, 2.5, "BMI ≥ 30 (obesity class I)"))
        elif bmi >= 25.0:
            signals.append(_Signal(RiskClass.ELEVATED_RISK, 1.5, "BMI 25–29.9 (overweight)"))
        elif bmi >= 18.5:
            signals.append(_Signal(RiskClass.LOW_RISK, 3.0, "BMI 18.5–24.9 (healthy range)"))
        else:
            signals.append(_Signal(RiskClass.LOW_RISK, 1.5, "BMI < 18.5 (underweight)"))
    if whtr is not None:
        if whtr >= 0.6:
            signals.append(
                _Signal(RiskClass.HIGH_RISK, 1.5, "WHtR ≥ 0.6 (severe central adiposity)")
            )
        elif whtr >= 0.5:
            signals.append(_Signal(RiskClass.ELEVATED_RISK, 1.0, "WHtR ≥ 0.5 (central adiposity)"))
        else:
            signals.append(
                _Signal(RiskClass.LOW_RISK, 1.5, "WHtR < 0.5 (healthy waist-to-height)")
            )
    return signals


def _hypertension_signals(
    systolic: float | None, diastolic: float | None, age: int
) -> list[_Signal]:
    """Hypertension needs a cuff reading; without BP the evidence stays thin
    (high vacuity → 'measurement required')."""
    signals: list[_Signal] = []
    if systolic is not None and diastolic is not None:
        if systolic >= 180.0 or diastolic >= 120.0:
            signals.append(
                _Signal(RiskClass.VERY_HIGH_RISK, 5.0, "Hypertensive crisis (≥ 180/120)")
            )
        elif systolic >= 140.0 or diastolic >= 90.0:
            signals.append(_Signal(RiskClass.HIGH_RISK, 3.0, "Stage 2 hypertension (≥ 140/90)"))
        elif systolic >= 130.0 or diastolic >= 80.0:
            signals.append(_Signal(RiskClass.ELEVATED_RISK, 1.5, "Stage 1 hypertension (≥ 130/80)"))
        elif systolic >= 120.0:
            signals.append(_Signal(RiskClass.ELEVATED_RISK, 0.75, "Elevated BP (120–129 systolic)"))
        else:
            signals.append(_Signal(RiskClass.LOW_RISK, 4.5, "BP < 120/80 (normal)"))
    if age >= 65:
        signals.append(_Signal(RiskClass.ELEVATED_RISK, 1.0, "Age ≥ 65"))
    elif age >= 45:
        signals.append(_Signal(RiskClass.ELEVATED_RISK, 0.5, "Age ≥ 45"))
    return signals


def _diabetes_signals(
    bmi: float | None, whtr: float | None, age: int
) -> list[_Signal]:
    """No fasting glucose is collected, so diabetes risk is inferred from
    adiposity and age proxies. Weights are intentionally damped to keep
    vacuity high — the result recommends confirmatory testing rather than
    impersonating a diagnostic."""
    signals: list[_Signal] = []
    if bmi is not None:
        if bmi >= 35.0:
            signals.append(
                _Signal(RiskClass.HIGH_RISK, 1.5, "BMI ≥ 35 (strong T2DM adiposity proxy)")
            )
        elif bmi >= 30.0:
            signals.append(
                _Signal(RiskClass.ELEVATED_RISK, 1.25, "BMI ≥ 30 (obesity raises T2DM risk)")
            )
        elif bmi >= 25.0:
            signals.append(
                _Signal(
                    RiskClass.ELEVATED_RISK, 0.75, "BMI ≥ 25 (overweight raises T2DM risk)"
                )
            )
        else:
            signals.append(_Signal(RiskClass.LOW_RISK, 2.0, "BMI < 25 (lower T2DM risk)"))
    if whtr is not None:
        if whtr >= 0.6:
            signals.append(
                _Signal(
                    RiskClass.HIGH_RISK,
                    1.5,
                    "WHtR ≥ 0.6 (central adiposity, insulin resistance)",
                )
            )
        elif whtr >= 0.5:
            signals.append(_Signal(RiskClass.ELEVATED_RISK, 1.0, "WHtR ≥ 0.5 (central adiposity)"))
        else:
            signals.append(_Signal(RiskClass.LOW_RISK, 1.5, "WHtR < 0.5 (lower T2DM risk)"))
    if age >= 45:
        signals.append(_Signal(RiskClass.ELEVATED_RISK, 0.75, "Age ≥ 45 (ADA screening threshold)"))
    else:
        signals.append(_Signal(RiskClass.LOW_RISK, 1.0, "Age < 45"))
    return signals


def build_anthropometric_signals(
    inputs: TapeMeasureInputs, derived: DerivedFeatures
) -> dict[Disease, list[_Signal]]:
    """Per-disease evidence from measured anthropometry and BP."""
    return {
        Disease.OBESITY: _obesity_signals(derived.bmi, derived.whtr),
        Disease.HYPERTENSION: _hypertension_signals(
            inputs.systolic_bp_mmhg, inputs.diastolic_bp_mmhg, inputs.age_years
        ),
        Disease.DIABETES: _diabetes_signals(derived.bmi, derived.whtr, inputs.age_years),
    }


def per_disease_label_from_features(
    *,
    bmi: float | None,
    whtr: float | None,
    systolic: float | None,
    diastolic: float | None,
    age: int,
) -> dict[Disease, RiskClass]:
    """Argmax per-disease risk-tier label from raw physiology.

    Used to derive training targets for the multi-head model directly from the
    clinical thresholds, so the trained network is a smooth, domain-invariant,
    calibrated version of the rule-based mapping the runtime falls back to.
    """
    signals = {
        Disease.OBESITY: _obesity_signals(bmi, whtr),
        Disease.HYPERTENSION: _hypertension_signals(systolic, diastolic, age),
        Disease.DIABETES: _diabetes_signals(bmi, whtr, age),
    }
    out: dict[Disease, RiskClass] = {}
    for disease in DISEASES:
        evidence = [0.0 for _ in RISK_CLASSES]
        for signal in signals[disease]:
            evidence[RISK_CLASSES.index(signal.target)] += signal.weight
        top = max(range(len(evidence)), key=evidence.__getitem__)
        out[disease] = RISK_CLASSES[top]
    return out


# Contextual symptoms → which disease(s) they nudge, and by how much. These are
# advisory lifestyle/history factors layered on top of the anthropometric model.
_CONTEXTUAL_ROUTING: dict[str, list[tuple[Disease, RiskClass, float, str]]] = {
    "family_history_diabetes": [
        (Disease.DIABETES, RiskClass.ELEVATED_RISK, 1.0, "Family history of diabetes"),
    ],
    "family_history_hypertension": [
        (Disease.HYPERTENSION, RiskClass.ELEVATED_RISK, 0.75, "Family history of hypertension"),
    ],
    "smoker_current": [
        (Disease.HYPERTENSION, RiskClass.ELEVATED_RISK, 0.5, "Current smoker"),
    ],
    "physical_activity_low": [
        (Disease.OBESITY, RiskClass.ELEVATED_RISK, 0.5, "Low physical activity"),
        (Disease.DIABETES, RiskClass.ELEVATED_RISK, 0.5, "Low physical activity"),
    ],
}


def build_contextual_signals(
    contextual_symptoms: frozenset[str],
) -> dict[Disease, list[_Signal]]:
    """Per-disease evidence from the structured contextual symptom audit."""
    routed = _empty_signals()
    for key in contextual_symptoms:
        for disease, target, weight, reason in _CONTEXTUAL_ROUTING.get(key, []):
            routed[disease].append(_Signal(target, weight, reason))
    return routed


def _assemble(
    base_evidence: dict[Disease, list[float]],
    anthropometric: dict[Disease, list[_Signal]],
    contextual: dict[Disease, list[_Signal]],
    *,
    model_kind: str,
    model_version: str,
    rule_evidence: bool,
) -> MultiDiseasePrediction:
    """Combine base (model or rule) evidence with contextual signals, finalize.

    ``rule_evidence`` toggles whether the anthropometric *weights* are folded
    into the evidence (rule-based backend) or only their reasons are surfaced
    (trained backend, whose evidence already encodes the anthropometry).
    """
    per_disease: dict[Disease, EvidentialPrediction] = {}
    factors: dict[Disease, list[str]] = {}
    for disease in DISEASES:
        evidence = list(base_evidence[disease])
        reasons: list[str] = []
        for signal in anthropometric[disease]:
            reasons.append(signal.reason)
            if rule_evidence:
                evidence[RISK_CLASSES.index(signal.target)] += signal.weight
        for signal in contextual[disease]:
            reasons.append(signal.reason)
            evidence[RISK_CLASSES.index(signal.target)] += signal.weight
        per_disease[disease] = finalize_prediction(evidence)
        factors[disease] = reasons
    return MultiDiseasePrediction(
        per_disease=per_disease,
        contributing_factors=factors,
        model_kind=model_kind,
        model_version=model_version,
    )


# ---------------------------------------------------------------------------
# Trained backend
# ---------------------------------------------------------------------------


class EvidentialTorchModel:
    """Loads a trained multi-head evidential classifier from disk.

    Expected on-disk layout::

        <checkpoint>.pt            # state_dict written via ``torch.save``
        <checkpoint>.pt.meta.json  # {
                                   #   "feature_names": [...],
                                   #   "label_mapping": ["LOW_RISK", ...],
                                   #   "disease_mapping": ["OBESITY", ...],
                                   #   "hidden_dims": [64, 32],
                                   #   "scaler": {"mean": [...], "std": [...]},
                                   #   "architecture": "dann_multihead_v1",
                                   #   "version": "...",
                                   # }

    The sidecar pins the exact feature ordering, disease-head ordering and
    standardization parameters used at training time. Any mismatch raises at
    construction — we refuse to silently mis-serve inference, and
    :func:`get_predictor` then falls back to the rule-based backend.
    """

    model_kind: str = "trained_torch_multihead_v1"

    def __init__(self, checkpoint_path: Path) -> None:
        import json

        import torch

        from victus_api.triage.edl.dirichlet import (
            build_multihead_dann_model,
            build_multihead_mlp,
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
        disease_mapping = tuple(meta.get("disease_mapping", []))
        expected_diseases = tuple(d.value for d in DISEASES)
        if disease_mapping != expected_diseases:
            raise ValueError(
                "Checkpoint disease_mapping does not match DISEASES; "
                f"expected {expected_diseases}, got {disease_mapping}",
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
        architecture = str(meta.get("architecture", "dann_multihead_v1"))
        num_diseases = len(DISEASES)

        if architecture == "sequential_multihead_v1":
            self._model = build_multihead_mlp(
                input_dim=len(FEATURE_NAMES),
                num_classes=len(RISK_CLASSES),
                num_diseases=num_diseases,
                hidden_dims=hidden_dims,
                dropout=0.0,
            )
            self._forward = self._forward_sequential
            self.model_kind = "trained_torch_multihead_v1"
            num_domains: int | None = None
        elif architecture == "dann_multihead_v1":
            domain_mapping = tuple(meta.get("domain_mapping", ()))
            if not domain_mapping:
                raise ValueError("dann_multihead_v1 checkpoint missing 'domain_mapping'")
            num_domains = len(domain_mapping)
            domain_hidden = int(meta.get("domain_hidden", 32))
            self._model = build_multihead_dann_model(
                input_dim=len(FEATURE_NAMES),
                num_classes=len(RISK_CLASSES),
                num_diseases=num_diseases,
                num_domains=num_domains,
                hidden_dims=hidden_dims,
                domain_hidden=domain_hidden,
                dropout=0.0,
            )
            self._forward = self._forward_dann
            self.model_kind = "trained_torch_dann_multihead_v1"
        else:
            raise ValueError(
                f"Unknown architecture {architecture!r}; expected "
                "'sequential_multihead_v1' or 'dann_multihead_v1'."
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
            num_diseases=num_diseases,
        )

    def _forward_sequential(self, x: Any) -> Any:
        return self._model(x)

    def _forward_dann(self, x: Any) -> Any:
        # Inference path skips the domain head entirely.
        return self._model.predict_evidence(x)

    def predict(
        self,
        inputs: TapeMeasureInputs,
        derived: DerivedFeatures,
        contextual_symptoms: frozenset[str],
    ) -> MultiDiseasePrediction:
        torch = self._torch
        features = to_feature_vector(inputs, derived)
        with torch.no_grad():
            x = torch.tensor([features], dtype=torch.float32, device=self._device)
            x = (x - self._scaler_mean) / self._scaler_std
            evidence_heads = self._forward(x)  # list[Tensor] length num_diseases
        base_evidence: dict[Disease, list[float]] = {
            disease: [float(e) for e in evidence_heads[i][0].tolist()]
            for i, disease in enumerate(DISEASES)
        }
        anthropometric = build_anthropometric_signals(inputs, derived)
        contextual = build_contextual_signals(contextual_symptoms)
        return _assemble(
            base_evidence,
            anthropometric,
            contextual,
            model_kind=self.model_kind,
            model_version=self.model_version,
            rule_evidence=False,
        )


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------


class RuleBasedEvidentialFallback:
    """Clinically-grounded per-disease evidence synthesis (no checkpoint).

    Evidence is intentionally damped (small magnitudes) so vacuity ``u = K/S``
    stays meaningfully > 0 — each disease reports with honest uncertainty
    rather than impersonating a confident trained model. Diabetes is damped
    further still, since it is inferred entirely from adiposity proxies.
    """

    model_kind: str = "rule_based_fallback_v1"
    model_version: str = "2.0.0"

    def predict(
        self,
        inputs: TapeMeasureInputs,
        derived: DerivedFeatures,
        contextual_symptoms: frozenset[str],
    ) -> MultiDiseasePrediction:
        base_evidence: dict[Disease, list[float]] = {
            disease: [0.0 for _ in RISK_CLASSES] for disease in DISEASES
        }
        anthropometric = build_anthropometric_signals(inputs, derived)
        contextual = build_contextual_signals(contextual_symptoms)
        return _assemble(
            base_evidence,
            anthropometric,
            contextual,
            model_kind=self.model_kind,
            model_version=self.model_version,
            rule_evidence=True,
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
