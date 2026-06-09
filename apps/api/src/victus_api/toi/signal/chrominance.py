"""Melanin-robust chrominance pulse extraction.

Two canonical methods, both operating on DC-normalised RGB::

    CHROM (de Haan & Jeanne, IEEE TBME 2013)
        X(t) = 3·R_n(t) − 2·G_n(t)
        Y(t) = 1.5·R_n(t) + G_n(t) − 1.5·B_n(t)
        α    = σ(X) / σ(Y)
        S(t) = X(t) − α·Y(t)

    POS (Wang et al., IEEE TBME 2017)
        P = [[0, 1, −1],
             [−2, 1, 1]]
        S = P @ C_n             # (2, N) projection onto the plane orthogonal to skin
        h(t) = S[0, t] + (σ(S[0]) / σ(S[1])) · S[1, t]

Both methods are intentionally green-channel-agnostic. The green band
(500–600 nm) is the strongest absorber for haemoglobin but also the most
attenuated by melanin, so signals built around only ``G_n − k·B_n`` collapse
on Fitzpatrick V–VI subjects. CHROM and POS combine all three channels
linearly so the pulse component survives the melanin attenuation.

The implementations below are vectorised numpy; both return a 1-D pulse
signal of the same length as the input window.
"""

from __future__ import annotations

import numpy as np

from victus_api.toi.signal.preprocess import dc_normalize


def chrom_pulse(rgb_uniform: np.ndarray) -> np.ndarray:
    """de Haan & Jeanne 2013 CHROM pulse signal."""
    if rgb_uniform.ndim != 2 or rgb_uniform.shape[1] != 3:
        raise ValueError("rgb_uniform must be (N, 3)")
    c_n = dc_normalize(rgb_uniform)
    r = c_n[:, 0]
    g = c_n[:, 1]
    b = c_n[:, 2]
    x = 3.0 * r - 2.0 * g
    y = 1.5 * r + g - 1.5 * b
    sx = float(x.std())
    sy = float(y.std())
    alpha = sx / sy if sy > 1e-9 else 0.0
    return x - alpha * y


def pos_pulse(rgb_uniform: np.ndarray) -> np.ndarray:
    """Wang et al. 2017 Plane-Orthogonal-to-Skin pulse signal."""
    if rgb_uniform.ndim != 2 or rgb_uniform.shape[1] != 3:
        raise ValueError("rgb_uniform must be (N, 3)")
    c_n = dc_normalize(rgb_uniform).T  # (3, N) for matrix multiply
    proj = np.array(
        [
            [0.0, 1.0, -1.0],
            [-2.0, 1.0, 1.0],
        ],
        dtype=np.float64,
    )
    s = proj @ c_n  # (2, N)
    s0_std = float(s[0].std())
    s1_std = float(s[1].std())
    alpha = s0_std / s1_std if s1_std > 1e-9 else 0.0
    return s[0] + alpha * s[1]
