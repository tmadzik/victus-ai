"""Welford-stable StandardScaler that persists to JSON.

Mask channels in :data:`victus_api.triage.features.FEATURE_NAMES` (the
``whr_mask`` and ``bp_mask`` indicators) are intentionally NOT standardised —
they carry semantic meaning (0/1) the model relies on. The scaler instead
emits ``mean=0, std=1`` for those columns so inference passes them through
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from victus_api.triage.features import FEATURE_NAMES

MASK_FEATURE_NAMES: frozenset[str] = frozenset({"whr_mask", "bp_mask"})
MASK_INDICES: tuple[int, ...] = tuple(
    i for i, name in enumerate(FEATURE_NAMES) if name in MASK_FEATURE_NAMES
)


@dataclass(slots=True)
class StandardScaler:
    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, x: np.ndarray) -> StandardScaler:
        if x.ndim != 2 or x.shape[1] != len(FEATURE_NAMES):
            raise ValueError(
                f"Expected shape (N, {len(FEATURE_NAMES)}); got {x.shape}",
            )
        mean = x.mean(axis=0)
        std = x.std(axis=0, ddof=0)
        std = np.where(std < 1e-6, 1.0, std)
        for idx in MASK_INDICES:
            mean[idx] = 0.0
            std[idx] = 1.0
        return cls(mean=mean.astype(np.float32), std=std.astype(np.float32))

    def transform(self, x: np.ndarray) -> np.ndarray:
        return ((x - self.mean) / self.std).astype(np.float32)

    def to_dict(self) -> dict[str, list[float]]:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}
