"""Top-level rPPG pipeline orchestration.

Single entry point :func:`run_rppg_pipeline` takes timestamped RGB samples
from the browser and emits the biomarker bundle the API persists. It runs
both CHROM and POS in parallel, selects the higher-SNR method for the
primary HR / HRV estimates, and exposes the other method's metrics for
audit + UI display.

Quality decision
----------------

``GOOD``     selected SNR ≥ 6 dB AND motion_score ≥ 0.7 AND lighting ≥ 0.7
             AND face_presence_ratio ≥ 0.85
``DEGRADED`` selected SNR ≥ 3 dB AND face_presence_ratio ≥ 0.6
``POOR``     anything else → no biomarkers reported, ask for re-capture
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import hilbert

from victus_api.core.logging import get_logger
from victus_api.toi import PIPELINE_VERSION
from victus_api.toi.signal.chrominance import chrom_pulse, pos_pulse
from victus_api.toi.signal.hrv import HrvMetrics, compute_hrv
from victus_api.toi.signal.preprocess import (
    estimate_lighting_score,
    uniformly_resample,
)
from victus_api.toi.signal.spectrum import (
    HR_BAND_HZ,
    RR_BAND_HZ,
    SpectralPeak,
    bpm_confidence_interval,
    butter_bandpass,
    dominant_peak,
)

log = get_logger(__name__)


# SNR thresholds reflect typical published in-band SNRs for forehead rPPG
# under indoor lighting: ≥ 3 dB is acceptable for clinical comparison, 0–3 dB
# is usable with widened CIs, and < 0 dB is uninterpretable. See
# de Haan & Jeanne 2013 §IV and Wang et al. 2017 §IV.B for the empirical
# distributions that informed these cutoffs.
GOOD_SNR_DB = 3.0
DEGRADED_SNR_DB = 0.0
GOOD_QUALITY_FLOOR = 0.7
GOOD_PRESENCE_FLOOR = 0.85
DEGRADED_PRESENCE_FLOOR = 0.6


@dataclass(frozen=True, slots=True)
class MethodResult:
    name: str  # "chrom" | "pos"
    hr_peak: SpectralPeak
    hrv: HrvMetrics
    pulse_std: float


@dataclass(frozen=True, slots=True)
class PipelineOutput:
    quality: str  # "GOOD" | "DEGRADED" | "POOR"
    method_selected: str
    duration_s: float
    sample_rate_hz: float
    frame_count: int
    frames_used: int
    snr_chrom_db: float
    snr_pos_db: float
    motion_score: float
    lighting_score: float
    face_presence_ratio: float
    heart_rate_bpm: float | None
    heart_rate_ci: tuple[float, float] | None
    respiratory_rate_bpm: float | None
    respiratory_rate_ci: tuple[float, float] | None
    hrv_rmssd_ms: float | None
    hrv_sdnn_ms: float | None
    stress_index: float | None
    warnings: list[str]
    method_details: dict[str, Any]
    pipeline_version: str


def _classify_quality(
    *, snr_db: float, motion: float, lighting: float, presence: float
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if presence < DEGRADED_PRESENCE_FLOOR:
        warnings.append("face_presence_too_low")
        return "POOR", warnings
    if snr_db < DEGRADED_SNR_DB:
        warnings.append("snr_below_floor")
        return "POOR", warnings
    if (
        snr_db >= GOOD_SNR_DB
        and motion >= GOOD_QUALITY_FLOOR
        and lighting >= GOOD_QUALITY_FLOOR
        and presence >= GOOD_PRESENCE_FLOOR
    ):
        return "GOOD", warnings
    if motion < GOOD_QUALITY_FLOOR:
        warnings.append("motion_unstable")
    if lighting < GOOD_QUALITY_FLOOR:
        warnings.append("lighting_unstable")
    if presence < GOOD_PRESENCE_FLOOR:
        warnings.append("face_presence_intermittent")
    return "DEGRADED", warnings


def run_rppg_pipeline(
    *,
    timestamps_seconds: np.ndarray,
    rgb_samples: np.ndarray,
    nominal_sample_rate_hz: float,
    motion_score: float,
    lighting_score_client: float | None,
    face_presence_ratio: float,
    target_resample_rate_hz: float = 30.0,
) -> PipelineOutput:
    if timestamps_seconds.shape[0] != rgb_samples.shape[0]:
        raise ValueError("timestamps and rgb_samples must align on axis 0")
    frame_count = int(timestamps_seconds.shape[0])
    if frame_count < int(5 * target_resample_rate_hz):
        return _poor_output(
            duration_s=float(
                timestamps_seconds[-1] - timestamps_seconds[0]
                if frame_count >= 2
                else 0.0
            ),
            sample_rate_hz=target_resample_rate_hz,
            frame_count=frame_count,
            frames_used=0,
            motion_score=motion_score,
            lighting_score=lighting_score_client or 0.0,
            face_presence_ratio=face_presence_ratio,
            warnings=["capture_too_short"],
        )

    t_uniform, rgb_uniform = uniformly_resample(
        timestamps_seconds, rgb_samples, target_rate_hz=target_resample_rate_hz
    )
    frames_used = int(t_uniform.shape[0])
    duration_s = float(t_uniform[-1] - t_uniform[0])

    lighting_score = (
        lighting_score_client
        if lighting_score_client is not None
        else estimate_lighting_score(rgb_uniform)
    )

    chrom_signal = chrom_pulse(rgb_uniform)
    pos_signal = pos_pulse(rgb_uniform)

    chrom_filtered = butter_bandpass(
        chrom_signal, sample_rate_hz=target_resample_rate_hz, band_hz=HR_BAND_HZ
    )
    pos_filtered = butter_bandpass(
        pos_signal, sample_rate_hz=target_resample_rate_hz, band_hz=HR_BAND_HZ
    )

    chrom_peak = dominant_peak(
        chrom_filtered,
        sample_rate_hz=target_resample_rate_hz,
        band_hz=HR_BAND_HZ,
    )
    pos_peak = dominant_peak(
        pos_filtered,
        sample_rate_hz=target_resample_rate_hz,
        band_hz=HR_BAND_HZ,
    )

    if pos_peak.snr_db > chrom_peak.snr_db:
        selected_name = "pos"
        selected_signal = pos_filtered
        selected_peak = pos_peak
        selected_raw = pos_signal
    else:
        selected_name = "chrom"
        selected_signal = chrom_filtered
        selected_peak = chrom_peak
        selected_raw = chrom_signal

    selected_hr_bpm = selected_peak.frequency_hz * 60.0
    hrv = compute_hrv(
        selected_signal,
        sample_rate_hz=target_resample_rate_hz,
        estimated_hr_bpm=selected_hr_bpm,
    )

    # Respiratory rate via two complementary methods, picking the higher SNR:
    #
    #  1. Slow-frequency component of the raw chrominance pulse — captures
    #     the breathing-induced blood-volume modulation that lives natively
    #     in the 0.1–0.5 Hz band of the un-HR-filtered signal.
    #  2. Hilbert-envelope demodulation of the HR-bandpassed pulse — recovers
    #     the amplitude modulation that breathing imprints on the cardiac
    #     pulse, which is invisible in (1) when the modulation is purely AM.
    #
    # Picking the better of the two by SNR is the canonical robustness move
    # for rPPG-RR (Karlen et al. 2013, Charlton et al. 2017).
    rr_baseline = butter_bandpass(
        selected_raw, sample_rate_hz=target_resample_rate_hz, band_hz=RR_BAND_HZ
    )
    rr_baseline_peak = dominant_peak(
        rr_baseline, sample_rate_hz=target_resample_rate_hz, band_hz=RR_BAND_HZ
    )
    envelope = np.abs(hilbert(selected_signal))
    envelope = envelope - envelope.mean()
    rr_envelope = butter_bandpass(
        envelope, sample_rate_hz=target_resample_rate_hz, band_hz=RR_BAND_HZ
    )
    rr_envelope_peak = dominant_peak(
        rr_envelope, sample_rate_hz=target_resample_rate_hz, band_hz=RR_BAND_HZ
    )
    rr_peak = (
        rr_envelope_peak
        if rr_envelope_peak.snr_db > rr_baseline_peak.snr_db
        else rr_baseline_peak
    )

    quality, warnings = _classify_quality(
        snr_db=selected_peak.snr_db,
        motion=motion_score,
        lighting=lighting_score,
        presence=face_presence_ratio,
    )

    if quality == "POOR":
        return _poor_output(
            duration_s=duration_s,
            sample_rate_hz=target_resample_rate_hz,
            frame_count=frame_count,
            frames_used=frames_used,
            motion_score=motion_score,
            lighting_score=lighting_score,
            face_presence_ratio=face_presence_ratio,
            warnings=warnings,
            snr_chrom_db=chrom_peak.snr_db,
            snr_pos_db=pos_peak.snr_db,
        )

    hr_ci = bpm_confidence_interval(
        selected_peak.frequency_hz,
        sample_rate_hz=target_resample_rate_hz,
        window_length_s=duration_s,
        snr_db=selected_peak.snr_db,
    )
    rr_ci = bpm_confidence_interval(
        rr_peak.frequency_hz,
        sample_rate_hz=target_resample_rate_hz,
        window_length_s=duration_s,
        snr_db=rr_peak.snr_db,
    )

    return PipelineOutput(
        quality=quality,
        method_selected=selected_name,
        duration_s=round(duration_s, 3),
        sample_rate_hz=target_resample_rate_hz,
        frame_count=frame_count,
        frames_used=frames_used,
        snr_chrom_db=round(chrom_peak.snr_db, 3),
        snr_pos_db=round(pos_peak.snr_db, 3),
        motion_score=round(motion_score, 3),
        lighting_score=round(lighting_score, 3),
        face_presence_ratio=round(face_presence_ratio, 3),
        heart_rate_bpm=round(selected_hr_bpm, 2),
        heart_rate_ci=(round(hr_ci[0], 2), round(hr_ci[1], 2)),
        respiratory_rate_bpm=round(rr_peak.frequency_hz * 60.0, 2),
        respiratory_rate_ci=(round(rr_ci[0], 2), round(rr_ci[1], 2)),
        hrv_rmssd_ms=round(hrv.rmssd_ms, 2) if hrv.rmssd_ms is not None else None,
        hrv_sdnn_ms=round(hrv.sdnn_ms, 2) if hrv.sdnn_ms is not None else None,
        stress_index=round(hrv.stress_index, 2) if hrv.stress_index is not None else None,
        warnings=warnings,
        method_details={
            "chrom": {
                "snr_db": round(chrom_peak.snr_db, 3),
                "peak_freq_hz": round(chrom_peak.frequency_hz, 4),
                "peak_bpm": round(chrom_peak.frequency_hz * 60.0, 2),
            },
            "pos": {
                "snr_db": round(pos_peak.snr_db, 3),
                "peak_freq_hz": round(pos_peak.frequency_hz, 4),
                "peak_bpm": round(pos_peak.frequency_hz * 60.0, 2),
            },
            "hrv_intervals_used": hrv.n_intervals,
            "respiratory_peak_snr_db": round(rr_peak.snr_db, 3),
        },
        pipeline_version=PIPELINE_VERSION,
    )


def _poor_output(
    *,
    duration_s: float,
    sample_rate_hz: float,
    frame_count: int,
    frames_used: int,
    motion_score: float,
    lighting_score: float,
    face_presence_ratio: float,
    warnings: list[str],
    snr_chrom_db: float = 0.0,
    snr_pos_db: float = 0.0,
) -> PipelineOutput:
    return PipelineOutput(
        quality="POOR",
        method_selected="none",
        duration_s=round(duration_s, 3),
        sample_rate_hz=sample_rate_hz,
        frame_count=frame_count,
        frames_used=frames_used,
        snr_chrom_db=round(snr_chrom_db, 3),
        snr_pos_db=round(snr_pos_db, 3),
        motion_score=round(motion_score, 3),
        lighting_score=round(lighting_score, 3),
        face_presence_ratio=round(face_presence_ratio, 3),
        heart_rate_bpm=None,
        heart_rate_ci=None,
        respiratory_rate_bpm=None,
        respiratory_rate_ci=None,
        hrv_rmssd_ms=None,
        hrv_sdnn_ms=None,
        stress_index=None,
        warnings=warnings,
        method_details={},
        pipeline_version=PIPELINE_VERSION,
    )
