"""Heart Rate Variability + stress index from peak intervals.

We detect systolic peaks in the bandpassed pulse signal via
``scipy.signal.find_peaks`` with a minimum-distance constraint anchored on
the spectral HR estimate. The resulting inter-beat intervals (IBI, ms) feed
the two textbook short-window HRV metrics:

* **SDNN**  — standard deviation of the IBIs (overall variability).
* **RMSSD** — root-mean-square of successive IBI differences (parasympathetic
  tone, the most informative short-window metric per Task Force 1996 and
  Shaffer & Ginsberg 2017).

The stress proxy maps RMSSD into [0, 100] via a log-scaled inversion:

    stress = 100 · clip(1 − log10(RMSSD / 5) / log10(120 / 5), 0, 1)

So RMSSD = 5 ms → ≈100 (high stress), 120 ms → 0 (rest). This is a
proxy — calibrated against published norms (Nunan et al. 2010) but not
a clinical-grade ANS index.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks


@dataclass(frozen=True, slots=True)
class HrvMetrics:
    rmssd_ms: float | None
    sdnn_ms: float | None
    n_intervals: int
    stress_index: float | None


def _stress_from_rmssd(rmssd_ms: float) -> float:
    if rmssd_ms <= 0.0:
        return 100.0
    lo, hi = 5.0, 120.0
    x = float(np.log10(max(rmssd_ms, lo) / lo))
    span = float(np.log10(hi / lo))
    return float(np.clip((1.0 - x / span) * 100.0, 0.0, 100.0))


def compute_hrv(
    pulse_signal: np.ndarray,
    *,
    sample_rate_hz: float,
    estimated_hr_bpm: float,
) -> HrvMetrics:
    if pulse_signal.ndim != 1 or len(pulse_signal) < int(2 * sample_rate_hz):
        return HrvMetrics(rmssd_ms=None, sdnn_ms=None, n_intervals=0, stress_index=None)

    # Refractory period of ~0.6 × expected RR interval bounds the maximum
    # plausible HR. Prominence of 0.3 σ admits AM-modulated peaks (where
    # respiratory modulation legitimately depresses systolic amplitude on
    # exhalation) without admitting noise — the distance constraint plus
    # the IBI plausibility filter below handle that. Pulse rate is then
    # double-checked against the spectral HR estimate; any IBI implying
    # a heart rate that differs from the spectral estimate by more than
    # 30 bpm is dropped as a peak-detection artefact.
    est_rr_seconds = 60.0 / max(estimated_hr_bpm, 30.0)
    min_distance = max(1, int(0.6 * est_rr_seconds * sample_rate_hz))
    # 0.15 σ admits AM-depressed peaks (respiratory exhalation legitimately
    # halves the systolic amplitude on the rPPG forehead patch); the IBI
    # plausibility window below filters any artefacts that slip through.
    prominence = float(pulse_signal.std()) * 0.15

    peaks, _ = find_peaks(pulse_signal, distance=min_distance, prominence=prominence)
    if len(peaks) < 4:
        return HrvMetrics(rmssd_ms=None, sdnn_ms=None, n_intervals=0, stress_index=None)

    rr_seconds = np.diff(peaks) / sample_rate_hz
    rr_ms = rr_seconds * 1000.0

    # Reject IBIs whose implied instantaneous HR is more than ±15 bpm from
    # the spectral estimate. This catches the dominant rPPG HRV artefact:
    # missed beats during AM dips produce IBIs of ~2× the true interval,
    # which would otherwise inflate RMSSD massively. ±15 bpm preserves real
    # short-window HRV (typical RMSSD 20–60 ms → ±10 bpm spread) without
    # admitting doubled intervals.
    hr_lo_bpm = max(estimated_hr_bpm - 15.0, 30.0)
    hr_hi_bpm = min(estimated_hr_bpm + 15.0, 240.0)
    ibi_lo_ms = 60_000.0 / hr_hi_bpm
    ibi_hi_ms = 60_000.0 / hr_lo_bpm
    keep = (rr_ms > 250.0) & (rr_ms < 2000.0) & (rr_ms >= ibi_lo_ms) & (rr_ms <= ibi_hi_ms)
    rr_ms = rr_ms[keep]
    if len(rr_ms) < 3:
        return HrvMetrics(rmssd_ms=None, sdnn_ms=None, n_intervals=0, stress_index=None)

    sdnn = float(np.std(rr_ms, ddof=1)) if len(rr_ms) >= 2 else 0.0
    diffs = np.diff(rr_ms)
    rmssd = float(np.sqrt(np.mean(diffs ** 2))) if len(diffs) >= 1 else 0.0
    stress = _stress_from_rmssd(rmssd) if rmssd > 0.0 else None

    return HrvMetrics(
        rmssd_ms=rmssd,
        sdnn_ms=sdnn,
        n_intervals=len(rr_ms),
        stress_index=stress,
    )
