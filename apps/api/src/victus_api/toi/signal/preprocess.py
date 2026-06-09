"""Preprocessing: resample to a uniform grid + DC normalize + detrend.

Browser-captured frames are timestamp-aware but never strictly uniform in
spacing — VSync jitter, dropped frames, and tab-throttling all introduce gaps.
We resample to a uniform grid at the nominal capture frame rate using linear
interpolation before any spectral work; chrominance methods assume uniform
sampling and FFTs require it outright.

DC normalization (``C_n = C / mean(C, axis=1) - 1``) converts the raw RGB
means into the fractional reflectance change that the pulse signal lives in —
this is the canonical step shared by both CHROM and POS.
"""

from __future__ import annotations

import numpy as np


def uniformly_resample(
    t_seconds: np.ndarray,
    rgb: np.ndarray,
    *,
    target_rate_hz: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Resample ``(t, rgb)`` onto a uniform grid at ``target_rate_hz``.

    Parameters
    ----------
    t_seconds
        Shape ``(N,)`` — frame timestamps in seconds (any monotonic origin).
    rgb
        Shape ``(N, 3)`` — per-frame mean R, G, B over the ROI.
    target_rate_hz
        Output sample rate.

    Returns
    -------
    t_uniform, rgb_uniform
        ``(M,)`` and ``(M, 3)`` arrays with ``M = floor(duration * rate) + 1``.
    """
    if t_seconds.ndim != 1 or rgb.ndim != 2 or rgb.shape[1] != 3:
        raise ValueError("t_seconds must be (N,) and rgb must be (N, 3)")
    if len(t_seconds) < 2:
        raise ValueError("Need at least 2 samples to resample")
    if target_rate_hz <= 0:
        raise ValueError("target_rate_hz must be positive")

    # Sort by time defensively (browsers can deliver out-of-order in rare cases).
    order = np.argsort(t_seconds)
    t_sorted = t_seconds[order]
    rgb_sorted = rgb[order]

    # Remove any duplicate timestamps to keep interp1d-style monotonicity.
    diffs = np.diff(t_sorted)
    keep = np.concatenate(([True], diffs > 0.0))
    t_clean = t_sorted[keep]
    rgb_clean = rgb_sorted[keep]

    t0, t1 = float(t_clean[0]), float(t_clean[-1])
    duration = t1 - t0
    if duration <= 0.0:
        raise ValueError("All timestamps are identical after dedup")
    n_out = int(np.floor(duration * target_rate_hz)) + 1
    t_uniform = t0 + np.arange(n_out) / target_rate_hz

    rgb_uniform = np.empty((n_out, 3), dtype=np.float64)
    for c in range(3):
        rgb_uniform[:, c] = np.interp(t_uniform, t_clean, rgb_clean[:, c])
    return t_uniform, rgb_uniform


def dc_normalize(channels: np.ndarray) -> np.ndarray:
    """Per-channel DC normalization: ``C_n[t] = C[t] / mean(C) - 1``.

    ``channels`` is ``(N, 3)``. Returns the same shape, zero-mean fractional
    reflectance change. Channels with non-positive DC (a near-black ROI)
    receive a zeroed column rather than NaNs from division-by-zero.
    """
    if channels.ndim != 2 or channels.shape[1] != 3:
        raise ValueError("channels must be (N, 3)")
    dc = channels.mean(axis=0)
    out = np.zeros_like(channels, dtype=np.float64)
    for c in range(3):
        if dc[c] > 1e-6:
            out[:, c] = channels[:, c] / dc[c] - 1.0
    return out


def estimate_lighting_score(channels: np.ndarray) -> float:
    """Lighting stability ∈ [0, 1] — 1.0 means rock-steady.

    Computed as ``1 − clip(CV_luminance, 0, 1)`` where CV is the coefficient
    of variation of the per-frame luminance over the capture window.
    Luminance approximation: ``0.2126 R + 0.7152 G + 0.0722 B`` (Rec. 709).
    """
    if channels.shape[0] < 2:
        return 0.0
    lum = (
        0.2126 * channels[:, 0] + 0.7152 * channels[:, 1] + 0.0722 * channels[:, 2]
    )
    mu = float(lum.mean())
    if mu <= 1e-6:
        return 0.0
    cv = float(lum.std()) / mu
    return float(np.clip(1.0 - cv, 0.0, 1.0))
