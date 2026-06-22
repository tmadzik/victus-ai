"""Pathway B — TOI biomarker corrector: a trainable, validated calibration head.

The CHROM/POS signal pipeline (:mod:`victus_api.toi.signal`) produces *raw*
biomarker estimates. Those estimates carry a well-documented, skin-tone-dependent
bias — green-channel rPPG loses contrast on Fitzpatrick V–VI, inflating heart-rate
error exactly where Sub-Saharan deployments need it lowest. This module learns a
small **residual corrector** that maps (raw rPPG estimate + signal quality + skin
tone) → the reference-device truth, with a per-target predictive variance so the
correction carries its own uncertainty.

It is the Pathway-B analogue of the Pathway-A training pipeline:

* the corpus is the ``rppg_calibration_records`` table (rPPG ↔ reference pairs),
  exported to JSONL — the same shape :func:`synthesize_calibration_corpus`
  produces, so the model can be bootstrapped on synthetic data *before* real
  calibration pairs arrive and then re-fit on the real ones with no code change;
* :func:`evaluate_corrector` reports held-out agreement (MAE / RMSE / Bland-Altman
  limits) **raw vs corrected**, stratified by skin tone — the evidence that the
  model "holds": correction must narrow the error, most of all on V–VI.

No network/DB import here: this is a pure-Python/torch training surface invoked by
:mod:`victus_api.training.cli`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from victus_api.calibration.statistics import CalibrationPair, compute_stats

# --- feature / target contract ---------------------------------------------
# Model inputs, in order. The first four columns double as the residual base:
# the corrector predicts a delta added to the raw rPPG estimate, not an absolute.
FEATURE_NAMES: tuple[str, ...] = (
    "rppg_hr_bpm",
    "rppg_rr_bpm",
    "rppg_hrv_rmssd_ms",
    "rppg_hrv_sdnn_ms",
    "snr_chrom_db",
    "snr_pos_db",
    "method_is_pos",
    "fitzpatrick_ordinal",
)
# Targets (reference-device truth), aligned to residual-base input columns 0..3.
TARGET_NAMES: tuple[str, ...] = (
    "hr_bpm",
    "rr_bpm",
    "hrv_rmssd_ms",
    "hrv_sdnn_ms",
)
RESIDUAL_BASE_COLS: tuple[int, ...] = (0, 1, 2, 3)

FITZPATRICK_ORDINAL: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
}
MODEL_KIND = "toi_corrector_v1"


@dataclass(frozen=True, slots=True)
class CorrectorRow:
    """One calibration pair flattened to the corrector's feature/target space."""

    features: np.ndarray  # shape (len(FEATURE_NAMES),), float32
    targets: np.ndarray  # shape (len(TARGET_NAMES),), float32, NaN where absent
    skin_tone: str | None
    reference_device_type: str


@dataclass(slots=True)
class FeatureScaler:
    """Standardiser for the corrector's inputs (its own; the triage scaler is
    bound to the triage feature space)."""

    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, x: np.ndarray) -> FeatureScaler:
        mean = x.mean(axis=0)
        std = x.std(axis=0, ddof=0)
        std = np.where(std < 1e-6, 1.0, std)
        return cls(mean=mean.astype(np.float32), std=std.astype(np.float32))

    def transform(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.std).astype(np.float32)

    def to_dict(self) -> dict[str, list[float]]:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}


class ToiCorrectorNet(nn.Module):
    """Heteroscedastic residual MLP: shared trunk → per-target (delta, log-var).

    The corrected estimate is ``base + delta`` where ``base`` is the raw rPPG
    value for that biomarker; ``log_var`` yields a per-target predictive σ so the
    correction reports its own confidence (wide where the signal was poor).
    """

    def __init__(self, input_dim: int, num_targets: int, hidden: int = 64) -> None:
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
        )
        self.delta_head = nn.Linear(hidden, num_targets)
        self.log_var_head = nn.Linear(hidden, num_targets)

    def forward(
        self, x: torch.Tensor, base: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        z = self.trunk(x)
        delta = self.delta_head(z)
        log_var = self.log_var_head(z).clamp(min=-6.0, max=6.0)
        return base + delta, log_var


def _masked_gaussian_nll(
    mean: torch.Tensor,
    log_var: torch.Tensor,
    target: torch.Tensor,
    mask: torch.Tensor,
) -> torch.Tensor:
    """Gaussian negative log-likelihood, averaged over present targets only."""
    inv_var = torch.exp(-log_var)
    nll = 0.5 * (inv_var * (mean - target) ** 2 + log_var)
    nll = nll * mask
    denom = mask.sum().clamp(min=1.0)
    return nll.sum() / denom


# --- corpus: synthetic bootstrap + real-export loader ----------------------
def _draw_fitzpatrick(rng: np.random.Generator, n: int) -> np.ndarray:
    """Skin-tone draw weighted toward IV–VI for a Sub-Saharan cohort."""
    weights = np.array([0.05, 0.08, 0.15, 0.27, 0.25, 0.20])
    return rng.choice(np.arange(1, 7), size=n, p=weights)


def synthesize_calibration_corpus(n: int, seed: int = 17) -> list[dict[str, Any]]:
    """Generate realistic (rPPG, reference) JSONL-shaped rows.

    The synthetic bias is the *real* failure mode: on darker skin the green-channel
    pulse contrast drops, so SNR falls and rPPG over-estimates HR with growing
    variance. A corrector that learns this skin-tone term should shrink the error —
    which is precisely what :func:`evaluate_corrector` checks. Targets RR / HRV are
    randomly absent (manual-pulse-count or HR-only references), exercising the
    masked loss.
    """
    rng = np.random.default_rng(seed)
    fitz = _draw_fitzpatrick(rng, n)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        f = int(fitz[i])
        ref_hr = float(np.clip(rng.normal(74, 13), 45, 165))
        ref_rr = float(np.clip(rng.normal(15, 3.0), 8, 28))
        ref_rmssd = float(np.clip(rng.lognormal(np.log(35), 0.45), 8, 110))
        ref_sdnn = float(np.clip(rng.lognormal(np.log(55), 0.40), 15, 160))

        # Skin-tone term: bias and noise grow from ~0 at I to a clear gap at VI.
        skin = (f - 1) / 5.0  # 0 → 1
        hr_bias = 0.6 + 6.5 * skin
        hr_sd = 1.2 + 4.8 * skin
        snr_chrom = float(rng.normal(7.5 - 6.0 * skin, 1.5))
        snr_pos = float(rng.normal(8.5 - 4.5 * skin, 1.5))

        rppg_hr = float(ref_hr + rng.normal(hr_bias, hr_sd))
        rppg_rr = float(ref_rr + rng.normal(0.4 + 1.5 * skin, 1.0 + 1.2 * skin))
        rppg_rmssd = float(ref_rmssd * rng.normal(1.0 + 0.20 * skin, 0.10 + 0.10 * skin))
        rppg_sdnn = float(ref_sdnn * rng.normal(1.0 + 0.15 * skin, 0.08 + 0.08 * skin))

        has_rr = rng.random() > 0.20
        has_hrv = rng.random() > 0.40
        rows.append(
            {
                "rppg_hr_bpm": rppg_hr,
                "rppg_rr_bpm": rppg_rr if has_rr else None,
                "rppg_hrv_rmssd_ms": rppg_rmssd if has_hrv else None,
                "rppg_hrv_sdnn_ms": rppg_sdnn if has_hrv else None,
                "snr_chrom_db": snr_chrom,
                "snr_pos_db": snr_pos,
                "method_selected": "pos" if snr_pos >= snr_chrom else "chrom",
                "skin_tone": ["I", "II", "III", "IV", "V", "VI"][f - 1],
                "reference_hr_bpm": ref_hr,
                "reference_rr_bpm": ref_rr if has_rr else None,
                "reference_hrv_rmssd_ms": ref_rmssd if has_hrv else None,
                "reference_hrv_sdnn_ms": ref_sdnn if has_hrv else None,
            }
        )
    return rows


def load_calibration_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a calibration export (one JSON object per line)."""
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _impute_optional(value: float | None, fallback: float) -> tuple[float, bool]:
    """Return (value-or-fallback, present-flag) for a nullable input."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return fallback, False
    return float(value), True


def rows_to_matrix(rows: list[dict[str, Any]]) -> list[CorrectorRow]:
    """Flatten raw JSONL/synthetic rows into the corrector feature/target space.

    Optional rPPG inputs are imputed with the column mean over present rows so the
    residual base is well-defined; the corresponding *target* is still masked when
    its reference truth is absent, so the loss never trains on a guessed label.
    """
    # Column means for optional inputs (rr, rmssd, sdnn) over present values only.
    def _col_mean(key: str) -> float:
        vals = [
            float(r[key])
            for r in rows
            if r.get(key) is not None and not _is_nan(r.get(key))
        ]
        return float(np.mean(vals)) if vals else 0.0

    rr_mean = _col_mean("rppg_rr_bpm")
    rmssd_mean = _col_mean("rppg_hrv_rmssd_ms")
    sdnn_mean = _col_mean("rppg_hrv_sdnn_ms")

    out: list[CorrectorRow] = []
    for r in rows:
        rppg_hr = float(r["rppg_hr_bpm"])
        rppg_rr, _ = _impute_optional(r.get("rppg_rr_bpm"), rr_mean)
        rppg_rmssd, _ = _impute_optional(r.get("rppg_hrv_rmssd_ms"), rmssd_mean)
        rppg_sdnn, _ = _impute_optional(r.get("rppg_hrv_sdnn_ms"), sdnn_mean)
        skin = r.get("skin_tone")
        fitz_ord = FITZPATRICK_ORDINAL.get(skin, 0) if skin else 0
        method_is_pos = 1.0 if str(r.get("method_selected", "chrom")) == "pos" else 0.0
        features = np.array(
            [
                rppg_hr,
                rppg_rr,
                rppg_rmssd,
                rppg_sdnn,
                float(r["snr_chrom_db"]),
                float(r["snr_pos_db"]),
                method_is_pos,
                float(fitz_ord),
            ],
            dtype=np.float32,
        )
        targets = np.array(
            [
                _nan_if_absent(r.get("reference_hr_bpm")),
                _nan_if_absent(r.get("reference_rr_bpm")),
                _nan_if_absent(r.get("reference_hrv_rmssd_ms")),
                _nan_if_absent(r.get("reference_hrv_sdnn_ms")),
            ],
            dtype=np.float32,
        )
        out.append(
            CorrectorRow(
                features=features,
                targets=targets,
                skin_tone=skin,
                reference_device_type=str(r.get("reference_device_type", "UNKNOWN")),
            )
        )
    return out


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and np.isnan(value)


def _nan_if_absent(value: float | None) -> float:
    if value is None or _is_nan(value):
        return float("nan")
    return float(value)


# --- training --------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TrainResult:
    model: ToiCorrectorNet
    scaler: FeatureScaler
    history: list[dict[str, float]]


def train_corrector(
    rows: list[CorrectorRow],
    *,
    epochs: int = 120,
    lr: float = 3e-3,
    weight_decay: float = 1e-4,
    hidden: int = 64,
    seed: int = 17,
) -> TrainResult:
    """Fit the residual corrector with a masked Gaussian NLL objective."""
    torch.manual_seed(seed)
    x = np.stack([r.features for r in rows]).astype(np.float32)
    y = np.stack([r.targets for r in rows]).astype(np.float32)
    mask = (~np.isnan(y)).astype(np.float32)
    y_filled = np.nan_to_num(y, nan=0.0)
    base = x[:, RESIDUAL_BASE_COLS].astype(np.float32)

    scaler = FeatureScaler.fit(x)
    x_s = scaler.transform(x)

    xt = torch.from_numpy(x_s)
    base_t = torch.from_numpy(base)
    yt = torch.from_numpy(y_filled)
    mask_t = torch.from_numpy(mask)

    model = ToiCorrectorNet(len(FEATURE_NAMES), len(TARGET_NAMES), hidden=hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)

    history: list[dict[str, float]] = []
    model.train()
    for epoch in range(epochs):
        opt.zero_grad()
        mean, log_var = model(xt, base_t)
        loss = _masked_gaussian_nll(mean, log_var, yt, mask_t)
        loss.backward()
        opt.step()
        if epoch % 10 == 0 or epoch == epochs - 1:
            history.append({"epoch": float(epoch), "nll": float(loss.item())})
    return TrainResult(model=model, scaler=scaler, history=history)


@torch.no_grad()
def predict_corrected(
    model: ToiCorrectorNet, scaler: FeatureScaler, features: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return (corrected means, predictive σ) for a feature matrix (N, F)."""
    model.eval()
    base = features[:, RESIDUAL_BASE_COLS].astype(np.float32)
    x_s = scaler.transform(features.astype(np.float32))
    mean, log_var = model(torch.from_numpy(x_s), torch.from_numpy(base))
    sigma = torch.exp(0.5 * log_var)
    return mean.numpy(), sigma.numpy()


# --- validation: does the correction hold? ---------------------------------
_SKIN_GROUPS: dict[str, frozenset[str]] = {
    "I_II": frozenset({"I", "II"}),
    "III_IV": frozenset({"III", "IV"}),
    "V_VI": frozenset({"V", "VI"}),
}


def _hr_pairs(
    rows: list[CorrectorRow], corrected_hr: np.ndarray, *, use_corrected: bool
) -> list[CalibrationPair]:
    pairs: list[CalibrationPair] = []
    for i, r in enumerate(rows):
        ref_hr = float(r.targets[0])
        if np.isnan(ref_hr):
            continue
        rppg_hr = float(corrected_hr[i]) if use_corrected else float(r.features[0])
        pairs.append(
            CalibrationPair(
                rppg_hr_bpm=rppg_hr,
                reference_hr_bpm=ref_hr,
                quality="GOOD",
                skin_tone=r.skin_tone,
                reference_device_type=r.reference_device_type,
            )
        )
    return pairs


def _stats_block(
    rows: list[CorrectorRow], corrected_hr: np.ndarray
) -> dict[str, Any]:
    raw = compute_stats(_hr_pairs(rows, corrected_hr, use_corrected=False))
    corrected = compute_stats(_hr_pairs(rows, corrected_hr, use_corrected=True))
    return {
        "n": 0 if raw is None else raw.n,
        "raw_mae_bpm": None if raw is None else round(raw.mae_bpm, 3),
        "corrected_mae_bpm": None if corrected is None else round(corrected.mae_bpm, 3),
        "raw_bias_bpm": None if raw is None else round(raw.bias_bpm, 3),
        "corrected_bias_bpm": None
        if corrected is None
        else round(corrected.bias_bpm, 3),
        "raw_loa_width_bpm": None
        if raw is None
        else round(raw.loa_upper_bpm - raw.loa_lower_bpm, 3),
        "corrected_loa_width_bpm": None
        if corrected is None
        else round(corrected.loa_upper_bpm - corrected.loa_lower_bpm, 3),
    }


def evaluate_corrector(
    result: TrainResult, val_rows: list[CorrectorRow]
) -> dict[str, Any]:
    """Held-out HR agreement, raw vs corrected, overall and by skin-tone group."""
    features = np.stack([r.features for r in val_rows]).astype(np.float32)
    corrected_hr, _ = predict_corrected(result.model, result.scaler, features)
    corrected_hr = corrected_hr[:, 0]

    by_skin: dict[str, Any] = {}
    for group, members in _SKIN_GROUPS.items():
        idx = [i for i, r in enumerate(val_rows) if (r.skin_tone or "") in members]
        if idx:
            sub = [val_rows[i] for i in idx]
            by_skin[group] = _stats_block(sub, corrected_hr[idx])

    return {
        "target": "hr_bpm",
        "overall": _stats_block(val_rows, corrected_hr),
        "by_skin_tone": by_skin,
    }


def split_rows(
    rows: list[CorrectorRow], *, val_frac: float, seed: int
) -> tuple[list[CorrectorRow], list[CorrectorRow]]:
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(rows))
    n_val = max(1, int(len(rows) * val_frac))
    val_idx = set(perm[:n_val].tolist())
    train = [r for i, r in enumerate(rows) if i not in val_idx]
    val = [rows[i] for i in sorted(val_idx)]
    return train, val


# --- checkpoint ------------------------------------------------------------
def save_corrector_checkpoint(
    result: TrainResult,
    path: Path,
    *,
    version: str,
    validation: dict[str, Any],
    n_train: int,
    n_val: int,
) -> None:
    """Write the state-dict plus a JSON meta sidecar (feature order, scaler,
    target order, held-out validation summary)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(result.model.state_dict(), path)
    meta: dict[str, Any] = {
        "model_kind": MODEL_KIND,
        "version": version,
        "feature_names": list(FEATURE_NAMES),
        "target_names": list(TARGET_NAMES),
        "residual_base_cols": list(RESIDUAL_BASE_COLS),
        "scaler": result.scaler.to_dict(),
        "hidden": result.model.delta_head.in_features,
        "n_train": n_train,
        "n_val": n_val,
        "validation": validation,
    }
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
