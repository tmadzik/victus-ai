"""Bandpass filtering + spectral peak / SNR analysis.

Defaults are clinical-band specific:

* ``HR_BAND_HZ = (0.7, 4.0)``    — 42–240 bpm cardiac range.
* ``RR_BAND_HZ = (0.1, 0.5)``    — 6–30 breaths/min respiratory range.

SNR is computed in the spectral domain as the ratio of power within ±0.2 Hz
of the dominant peak to the total power in the bandpass region outside that
window — a metric directly tied to physiological interpretability rather
than generic broadband noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, filtfilt, welch

HR_BAND_HZ: tuple[float, float] = (0.7, 4.0)
RR_BAND_HZ: tuple[float, float] = (0.1, 0.5)
SNR_PEAK_HALFBAND_HZ: float = 0.2


@dataclass(frozen=True, slots=True)
class SpectralPeak:
    frequency_hz: float
    power: float
    snr_db: float


def butter_bandpass(
    signal: np.ndarray,
    *,
    sample_rate_hz: float,
    band_hz: tuple[float, float],
    order: int = 4,
) -> np.ndarray:
    """Zero-phase 4th-order Butterworth bandpass via filtfilt."""
    if signal.ndim != 1:
        raise ValueError("signal must be 1-D")
    nyquist = 0.5 * sample_rate_hz
    low = band_hz[0] / nyquist
    high = band_hz[1] / nyquist
    if not (0.0 < low < high < 1.0):
        raise ValueError(
            f"band {band_hz} is incompatible with sample_rate {sample_rate_hz}"
        )
    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, signal)


def dominant_peak(
    signal: np.ndarray,
    *,
    sample_rate_hz: float,
    band_hz: tuple[float, float],
    snr_halfband_hz: float = SNR_PEAK_HALFBAND_HZ,
) -> SpectralPeak:
    """Find the dominant in-band spectral peak and compute its SNR.

    Welch's method is used for the power-spectral-density estimate (Hamming
    window, ``nperseg = min(len(signal), 8 * sample_rate)``) — this trades
    some frequency resolution for variance reduction, which matters on short
    (30 s) rPPG windows.
    """
    nperseg = int(min(len(signal), 8 * sample_rate_hz))
    if nperseg < 16:
        return SpectralPeak(frequency_hz=0.0, power=0.0, snr_db=0.0)
    f, pxx = welch(
        signal,
        fs=sample_rate_hz,
        nperseg=nperseg,
        window="hamming",
        detrend="linear",
    )
    band_mask = (f >= band_hz[0]) & (f <= band_hz[1])
    if not band_mask.any():
        return SpectralPeak(frequency_hz=0.0, power=0.0, snr_db=0.0)

    idx_in_band = np.argmax(pxx[band_mask])
    band_idxs = np.where(band_mask)[0]
    peak_idx = int(band_idxs[idx_in_band])
    peak_freq = float(f[peak_idx])
    peak_power = float(pxx[peak_idx])

    peak_band_mask = (
        (f >= peak_freq - snr_halfband_hz) & (f <= peak_freq + snr_halfband_hz)
    )
    sideband_mask = band_mask & ~peak_band_mask
    signal_power = float(pxx[peak_band_mask].sum())
    noise_power = float(pxx[sideband_mask].sum())
    if noise_power <= 1e-12:
        snr_db = 30.0
    else:
        snr_db = 10.0 * np.log10(max(signal_power, 1e-12) / noise_power)
    return SpectralPeak(
        frequency_hz=peak_freq,
        power=peak_power,
        snr_db=float(snr_db),
    )


def bpm_confidence_interval(
    peak_freq_hz: float,
    *,
    sample_rate_hz: float,
    window_length_s: float,
    snr_db: float,
) -> tuple[float, float]:
    """Heuristic ±CI on a BPM estimate from spectral resolution + SNR.

    Welch's nperseg = 8 · fs gives frequency resolution Δf ≈ fs / nperseg
    = 1/8 Hz = 7.5 bpm. We scale the CI inversely with SNR (linear in
    log-power) so a clean signal gets a tight band and a noisy one gets
    wider — this matches the underlying Cramér-Rao behaviour qualitatively
    without overclaiming a precise statistical bound.
    """
    df_hz = 1.0 / 8.0
    base_ci_bpm = df_hz * 60.0  # ≈ 7.5 bpm one-sided
    # Scale: SNR ≥ 15 dB → 0.5×, SNR ≤ 0 dB → 2×
    snr_factor = float(np.clip(2.0 - (snr_db / 15.0), 0.5, 4.0))
    half = base_ci_bpm * snr_factor
    centre = peak_freq_hz * 60.0
    return centre - half, centre + half
