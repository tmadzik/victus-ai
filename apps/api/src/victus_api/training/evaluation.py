"""Validation & calibration metrics for the Victus models.

Pure functions over numpy arrays — no model or DB coupling — so they are unit
testable and reusable by the triage and TOI evaluation harnesses alike.

* Triage (classification): ROC-AUC, Brier score, Expected Calibration Error and
  a reliability curve — calibration matters as much as discrimination for a
  decision-support tool that surfaces uncertainty.
* TOI (continuous, vs a reference device): Bland-Altman agreement (bias + 95 %
  limits of agreement) — the correct way to report method agreement, not r/MAE.
* Generalisation: a group-held-out split so models can be validated on unseen
  sites / countries (the train≠deploy-population concern).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def _ranks(values: np.ndarray) -> np.ndarray:
    """Average (tie-aware) 1-based ranks, like scipy.stats.rankdata."""
    order = values.argsort(kind="mergesort")
    sorted_vals = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    i = 0
    n = len(values)
    while i < n:
        j = i
        while j < n and sorted_vals[j] == sorted_vals[i]:
            j += 1
        ranks[order[i:j]] = (i + j - 1) / 2.0 + 1.0
        i = j
    return ranks


def roc_auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """Binary ROC-AUC via the Mann-Whitney U statistic (tie-aware).

    Returns NaN when only one class is present (AUROC undefined).
    """
    s = np.asarray(scores, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    n_pos = float((y == 1).sum())
    n_neg = float((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = _ranks(s)
    sum_pos = ranks[y == 1].sum()
    return (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def brier_score(probs: Sequence[float], labels: Sequence[int]) -> float:
    p = np.asarray(probs, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    return float(np.mean((p - y) ** 2))


@dataclass(frozen=True)
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float
    mean_accuracy: float


def reliability_curve(
    probs: Sequence[float], labels: Sequence[int], *, n_bins: int = 10
) -> list[ReliabilityBin]:
    p = np.asarray(probs, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out: list[ReliabilityBin] = []
    for k in range(n_bins):
        lo, hi = edges[k], edges[k + 1]
        mask = (p > lo) & (p <= hi) if k > 0 else (p >= lo) & (p <= hi)
        count = int(mask.sum())
        out.append(
            ReliabilityBin(
                lower=float(lo),
                upper=float(hi),
                count=count,
                mean_confidence=float(p[mask].mean()) if count else 0.0,
                mean_accuracy=float(y[mask].mean()) if count else 0.0,
            )
        )
    return out


def expected_calibration_error(
    probs: Sequence[float], labels: Sequence[int], *, n_bins: int = 10
) -> float:
    """Weighted mean gap between confidence and accuracy across probability bins."""
    p = np.asarray(probs, dtype=np.float64)
    n = len(p)
    if n == 0:
        return float("nan")
    ece = 0.0
    for b in reliability_curve(probs, labels, n_bins=n_bins):
        if b.count:
            ece += (b.count / n) * abs(b.mean_accuracy - b.mean_confidence)
    return ece


@dataclass(frozen=True)
class BlandAltman:
    n: int
    bias: float  # mean(method - reference)
    sd_diff: float
    loa_lower: float  # bias - 1.96·sd
    loa_upper: float  # bias + 1.96·sd
    mean_abs_error: float


def bland_altman(
    method: Sequence[float], reference: Sequence[float]
) -> BlandAltman:
    """Agreement of a method (e.g. rPPG HR) against a reference device."""
    m = np.asarray(method, dtype=np.float64)
    r = np.asarray(reference, dtype=np.float64)
    if m.shape != r.shape or m.size < 2:
        raise ValueError("method and reference must be equal-length (>=2) arrays")
    diff = m - r
    bias = float(diff.mean())
    sd = float(diff.std(ddof=1))
    return BlandAltman(
        n=int(m.size),
        bias=bias,
        sd_diff=sd,
        loa_lower=bias - 1.96 * sd,
        loa_upper=bias + 1.96 * sd,
        mean_abs_error=float(np.abs(diff).mean()),
    )


def group_holdout_split(
    groups: Sequence[str], holdout: set[str]
) -> tuple[list[int], list[int]]:
    """Indices for a group-held-out split (e.g. hold out a site or country).

    Returns ``(train_idx, test_idx)`` where test rows belong to a ``holdout``
    group — the right way to estimate generalisation to unseen deployment
    populations rather than a random split that leaks site identity.
    """
    train_idx: list[int] = []
    test_idx: list[int] = []
    for i, g in enumerate(groups):
        (test_idx if g in holdout else train_idx).append(i)
    return train_idx, test_idx
