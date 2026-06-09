"""Bland-Altman + agreement statistics for rPPG calibration pairs.

References
----------

* Bland, J.M. & Altman, D.G., 1986. *Statistical methods for assessing
  agreement between two methods of clinical measurement.* Lancet 1, 307–310.
  Source of the bias + 95% Limits of Agreement framework (LoA = bias ± 1.96 σ).
* Bland & Altman, 1999 §4. Recommend N ≥ 100 for tight LoA confidence; we
  surface N < 30 as a small-sample flag and N < 5 as "LoA unreliable".

The module is intentionally framework-free (no pandas, no DataFrames) — it
operates on lists of plain `(rppg_value, reference_value)` tuples so it can
be exercised in tests without standing up a database.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

import numpy as np
from scipy import stats as scipy_stats

# Bland-Altman cutoffs — surface to the UI rather than hide them.
MIN_PAIRS_FOR_STATS = 2
MIN_PAIRS_FOR_LOA = 5
MIN_PAIRS_FOR_PEARSON = 30


@dataclass(frozen=True, slots=True)
class CalibrationStats:
    n: int
    mae_bpm: float
    rmse_bpm: float
    bias_bpm: float
    std_diff_bpm: float
    loa_lower_bpm: float
    loa_upper_bpm: float
    pearson_r: float | None
    pearson_p: float | None
    ref_min: float
    ref_max: float
    ref_mean: float
    # Bland-Altman plotting points: ``means[i] = (rppg + ref)/2``,
    # ``differences[i] = rppg − ref``.
    means: list[float]
    differences: list[float]
    flags: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "mae_bpm": self.mae_bpm,
            "rmse_bpm": self.rmse_bpm,
            "bias_bpm": self.bias_bpm,
            "std_diff_bpm": self.std_diff_bpm,
            "loa_lower_bpm": self.loa_lower_bpm,
            "loa_upper_bpm": self.loa_upper_bpm,
            "pearson_r": self.pearson_r,
            "pearson_p": self.pearson_p,
            "ref_min": self.ref_min,
            "ref_max": self.ref_max,
            "ref_mean": self.ref_mean,
            "means": self.means,
            "differences": self.differences,
            "flags": self.flags,
        }


@dataclass(frozen=True, slots=True)
class StratifiedStats:
    overall: CalibrationStats | None
    overall_hrv: HrvCalibrationStats | None = None
    by_quality: dict[str, CalibrationStats | None] = field(default_factory=dict)
    by_fitzpatrick: dict[str, CalibrationStats | None] = field(default_factory=dict)
    by_reference_device: dict[str, CalibrationStats | None] = field(default_factory=dict)
    by_posture: dict[str, CalibrationStats | None] = field(default_factory=dict)
    by_time_of_day: dict[str, CalibrationStats | None] = field(default_factory=dict)
    by_subject: dict[str, CalibrationStats | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        def _maybe(s: CalibrationStats | None) -> dict[str, object] | None:
            return s.to_dict() if s is not None else None

        return {
            "overall": _maybe(self.overall),
            "overall_hrv": self.overall_hrv.to_dict() if self.overall_hrv else None,
            "by_quality": {k: _maybe(v) for k, v in self.by_quality.items()},
            "by_fitzpatrick": {
                (k if k is not None else "UNKNOWN"): _maybe(v)
                for k, v in self.by_fitzpatrick.items()
            },
            "by_reference_device": {
                k: _maybe(v) for k, v in self.by_reference_device.items()
            },
            "by_posture": {k: _maybe(v) for k, v in self.by_posture.items()},
            "by_time_of_day": {
                k: _maybe(v) for k, v in self.by_time_of_day.items()
            },
            "by_subject": {k: _maybe(v) for k, v in self.by_subject.items()},
        }


@dataclass(frozen=True, slots=True)
class CalibrationPair:
    rppg_hr_bpm: float
    reference_hr_bpm: float
    quality: str
    skin_tone: str | None  # "I" … "VI" or None
    reference_device_type: str
    # HRV agreement only contributes when both sides are present (BLE
    # auto-pair from a chest strap providing RR intervals).
    rppg_hrv_rmssd_ms: float | None = None
    reference_hrv_rmssd_ms: float | None = None
    rppg_hrv_sdnn_ms: float | None = None
    reference_hrv_sdnn_ms: float | None = None
    # Pre-registered study context — present when the capture was attached
    # to an active StudySession at record time.
    posture: str | None = None
    time_of_day: str | None = None
    subject_external_id: str | None = None


@dataclass(frozen=True, slots=True)
class HrvCalibrationStats:
    n: int
    rmssd_mae_ms: float
    rmssd_rmse_ms: float
    rmssd_bias_ms: float
    rmssd_std_diff_ms: float
    rmssd_loa_lower_ms: float
    rmssd_loa_upper_ms: float
    rmssd_pearson_r: float | None
    rmssd_pearson_p: float | None
    sdnn_mae_ms: float | None
    sdnn_bias_ms: float | None
    rmssd_means: list[float]
    rmssd_differences: list[float]
    flags: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "rmssd_mae_ms": self.rmssd_mae_ms,
            "rmssd_rmse_ms": self.rmssd_rmse_ms,
            "rmssd_bias_ms": self.rmssd_bias_ms,
            "rmssd_std_diff_ms": self.rmssd_std_diff_ms,
            "rmssd_loa_lower_ms": self.rmssd_loa_lower_ms,
            "rmssd_loa_upper_ms": self.rmssd_loa_upper_ms,
            "rmssd_pearson_r": self.rmssd_pearson_r,
            "rmssd_pearson_p": self.rmssd_pearson_p,
            "sdnn_mae_ms": self.sdnn_mae_ms,
            "sdnn_bias_ms": self.sdnn_bias_ms,
            "rmssd_means": self.rmssd_means,
            "rmssd_differences": self.rmssd_differences,
            "flags": self.flags,
        }


def _empty_stats(flags: list[str]) -> CalibrationStats:
    return CalibrationStats(
        n=0,
        mae_bpm=0.0,
        rmse_bpm=0.0,
        bias_bpm=0.0,
        std_diff_bpm=0.0,
        loa_lower_bpm=0.0,
        loa_upper_bpm=0.0,
        pearson_r=None,
        pearson_p=None,
        ref_min=0.0,
        ref_max=0.0,
        ref_mean=0.0,
        means=[],
        differences=[],
        flags=flags,
    )


def compute_stats(pairs: Iterable[CalibrationPair]) -> CalibrationStats | None:
    """Compute agreement statistics for an iterable of paired observations.

    Returns ``None`` if fewer than :data:`MIN_PAIRS_FOR_STATS` pairs are
    provided — there is no meaningful Bland-Altman computation on a singleton.
    """
    pair_list = list(pairs)
    n = len(pair_list)
    if n < MIN_PAIRS_FOR_STATS:
        if n == 0:
            return None
        return _empty_stats(["insufficient_samples"])

    rppg = np.array([p.rppg_hr_bpm for p in pair_list], dtype=np.float64)
    ref = np.array([p.reference_hr_bpm for p in pair_list], dtype=np.float64)

    differences = rppg - ref
    means = (rppg + ref) / 2.0

    mae = float(np.mean(np.abs(differences)))
    rmse = float(math.sqrt(float(np.mean(differences ** 2))))
    bias = float(np.mean(differences))
    std_diff = float(np.std(differences, ddof=1)) if n >= 2 else 0.0
    loa_lower = bias - 1.96 * std_diff
    loa_upper = bias + 1.96 * std_diff

    flags: list[str] = []
    if n < MIN_PAIRS_FOR_LOA:
        flags.append("loa_unreliable_below_5_samples")
    if n < MIN_PAIRS_FOR_PEARSON:
        flags.append("pearson_small_n")

    if n >= 3 and float(rppg.std()) > 0.0 and float(ref.std()) > 0.0:
        result = scipy_stats.pearsonr(rppg, ref)
        pearson_r: float | None = float(result.statistic)
        pearson_p: float | None = float(result.pvalue)
    else:
        pearson_r = None
        pearson_p = None
        flags.append("pearson_undefined_constant_input")

    return CalibrationStats(
        n=n,
        mae_bpm=round(mae, 3),
        rmse_bpm=round(rmse, 3),
        bias_bpm=round(bias, 3),
        std_diff_bpm=round(std_diff, 3),
        loa_lower_bpm=round(loa_lower, 3),
        loa_upper_bpm=round(loa_upper, 3),
        pearson_r=round(pearson_r, 4) if pearson_r is not None else None,
        pearson_p=round(pearson_p, 6) if pearson_p is not None else None,
        ref_min=float(ref.min()),
        ref_max=float(ref.max()),
        ref_mean=round(float(ref.mean()), 3),
        means=[round(float(m), 3) for m in means],
        differences=[round(float(d), 3) for d in differences],
        flags=flags,
    )


def compute_hrv_stats(
    pairs: Iterable[CalibrationPair],
) -> HrvCalibrationStats | None:
    """RMSSD/SDNN agreement on pairs where both sides have HRV."""
    eligible = [
        p
        for p in pairs
        if p.rppg_hrv_rmssd_ms is not None and p.reference_hrv_rmssd_ms is not None
    ]
    n = len(eligible)
    if n < MIN_PAIRS_FOR_STATS:
        return None

    rppg_rmssd = np.array(
        [p.rppg_hrv_rmssd_ms for p in eligible], dtype=np.float64
    )
    ref_rmssd = np.array(
        [p.reference_hrv_rmssd_ms for p in eligible], dtype=np.float64
    )
    diff = rppg_rmssd - ref_rmssd
    means = (rppg_rmssd + ref_rmssd) / 2.0

    mae = float(np.mean(np.abs(diff)))
    rmse = float(math.sqrt(float(np.mean(diff ** 2))))
    bias = float(np.mean(diff))
    std_diff = float(np.std(diff, ddof=1)) if n >= 2 else 0.0
    loa_lower = bias - 1.96 * std_diff
    loa_upper = bias + 1.96 * std_diff

    flags: list[str] = []
    if n < MIN_PAIRS_FOR_LOA:
        flags.append("loa_unreliable_below_5_samples")
    if n < MIN_PAIRS_FOR_PEARSON:
        flags.append("pearson_small_n")

    if n >= 3 and float(rppg_rmssd.std()) > 0.0 and float(ref_rmssd.std()) > 0.0:
        r = scipy_stats.pearsonr(rppg_rmssd, ref_rmssd)
        pearson_r: float | None = float(r.statistic)
        pearson_p: float | None = float(r.pvalue)
    else:
        pearson_r = None
        pearson_p = None
        flags.append("pearson_undefined_constant_input")

    sdnn_eligible = [
        p
        for p in eligible
        if p.rppg_hrv_sdnn_ms is not None and p.reference_hrv_sdnn_ms is not None
    ]
    if sdnn_eligible:
        rppg_sdnn = np.array(
            [p.rppg_hrv_sdnn_ms for p in sdnn_eligible], dtype=np.float64
        )
        ref_sdnn = np.array(
            [p.reference_hrv_sdnn_ms for p in sdnn_eligible], dtype=np.float64
        )
        sdnn_diff = rppg_sdnn - ref_sdnn
        sdnn_mae: float | None = round(float(np.mean(np.abs(sdnn_diff))), 3)
        sdnn_bias: float | None = round(float(np.mean(sdnn_diff)), 3)
    else:
        sdnn_mae = None
        sdnn_bias = None

    return HrvCalibrationStats(
        n=n,
        rmssd_mae_ms=round(mae, 3),
        rmssd_rmse_ms=round(rmse, 3),
        rmssd_bias_ms=round(bias, 3),
        rmssd_std_diff_ms=round(std_diff, 3),
        rmssd_loa_lower_ms=round(loa_lower, 3),
        rmssd_loa_upper_ms=round(loa_upper, 3),
        rmssd_pearson_r=round(pearson_r, 4) if pearson_r is not None else None,
        rmssd_pearson_p=round(pearson_p, 6) if pearson_p is not None else None,
        sdnn_mae_ms=sdnn_mae,
        sdnn_bias_ms=sdnn_bias,
        rmssd_means=[round(float(m), 3) for m in means],
        rmssd_differences=[round(float(d), 3) for d in diff],
        flags=flags,
    )


def compute_stratified(
    pairs: Iterable[CalibrationPair],
) -> StratifiedStats:
    pair_list = list(pairs)
    overall = compute_stats(pair_list)
    overall_hrv = compute_hrv_stats(pair_list)

    by_quality: dict[str, CalibrationStats | None] = {}
    for q in ("GOOD", "DEGRADED", "POOR"):
        subset = [p for p in pair_list if p.quality == q]
        by_quality[q] = compute_stats(subset)

    fitz_keys = ("I", "II", "III", "IV", "V", "VI", None)
    by_fitzpatrick: dict[str, CalibrationStats | None] = {}
    for fz in fitz_keys:
        subset = [p for p in pair_list if p.skin_tone == fz]
        key = fz if fz is not None else "UNKNOWN"
        by_fitzpatrick[key] = compute_stats(subset)

    devices = (
        "PULSE_OXIMETER",
        "SMART_WATCH",
        "ECG_STRAP",
        "MEDICAL_ECG",
        "MANUAL_PULSE_COUNT",
    )
    by_reference_device: dict[str, CalibrationStats | None] = {}
    for dev in devices:
        subset = [p for p in pair_list if p.reference_device_type == dev]
        by_reference_device[dev] = compute_stats(subset)

    # Study context strata — only emit cells that have at least one pair so
    # the UI doesn't render an empty row for every enum value.
    postures = ("SITTING", "STANDING", "SUPINE", "SEMI_RECLINED")
    by_posture: dict[str, CalibrationStats | None] = {}
    for pose in postures:
        subset = [p for p in pair_list if p.posture == pose]
        if subset:
            by_posture[pose] = compute_stats(subset)

    tods = ("MORNING", "AFTERNOON", "EVENING", "NIGHT")
    by_time_of_day: dict[str, CalibrationStats | None] = {}
    for tod in tods:
        subset = [p for p in pair_list if p.time_of_day == tod]
        if subset:
            by_time_of_day[tod] = compute_stats(subset)

    by_subject: dict[str, CalibrationStats | None] = {}
    subjects = sorted({p.subject_external_id for p in pair_list if p.subject_external_id})
    for sid in subjects:
        subset = [p for p in pair_list if p.subject_external_id == sid]
        if subset:
            by_subject[sid] = compute_stats(subset)

    return StratifiedStats(
        overall=overall,
        overall_hrv=overall_hrv,
        by_quality=by_quality,
        by_fitzpatrick=by_fitzpatrick,
        by_reference_device=by_reference_device,
        by_posture=by_posture,
        by_time_of_day=by_time_of_day,
        by_subject=by_subject,
    )


def rmssd_from_rr_intervals(rr_intervals_ms: list[float]) -> float | None:
    """Compute ``RMSSD = √mean((ΔRR)²)`` from raw RR intervals.

    Returns ``None`` if there are fewer than 2 successive intervals.
    Server-side recompute provides a canonical persisted value even if a
    future client bug changes the computation.
    """
    if len(rr_intervals_ms) < 2:
        return None
    arr = np.asarray(rr_intervals_ms, dtype=np.float64)
    diffs = np.diff(arr)
    return float(np.sqrt(float(np.mean(diffs ** 2))))


def sdnn_from_rr_intervals(rr_intervals_ms: list[float]) -> float | None:
    if len(rr_intervals_ms) < 2:
        return None
    arr = np.asarray(rr_intervals_ms, dtype=np.float64)
    return float(np.std(arr, ddof=1))
