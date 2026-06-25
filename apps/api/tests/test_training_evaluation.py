"""Unit tests for the validation/calibration metrics + model card (pure numpy)."""

from __future__ import annotations

import math

import pytest

from victus_api.training.evaluation import (
    bland_altman,
    brier_score,
    expected_calibration_error,
    group_holdout_split,
    reliability_curve,
    roc_auc,
)
from victus_api.training.model_card import triage_model_card

# --- ROC-AUC ----------------------------------------------------------------


def test_roc_auc_perfect_separation() -> None:
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    assert roc_auc(scores, labels) == 1.0


def test_roc_auc_inverted_is_zero() -> None:
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [0, 0, 1, 1]
    assert roc_auc(scores, labels) == 0.0


def test_roc_auc_ties_give_half() -> None:
    # All identical scores → AUC 0.5 (tie-aware average ranks).
    assert roc_auc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]) == 0.5


def test_roc_auc_single_class_is_nan() -> None:
    assert math.isnan(roc_auc([0.1, 0.2], [1, 1]))


# --- calibration ------------------------------------------------------------


def test_ece_zero_for_perfectly_calibrated() -> None:
    # In each bin, predicted confidence equals empirical accuracy.
    probs = [0.0, 0.0, 1.0, 1.0]
    labels = [0, 0, 1, 1]
    assert expected_calibration_error(probs, labels, n_bins=10) == 0.0


def test_ece_positive_for_overconfident() -> None:
    probs = [0.99, 0.99, 0.99, 0.99]
    labels = [1, 0, 0, 0]  # 25% accuracy at 99% confidence
    assert expected_calibration_error(probs, labels, n_bins=10) > 0.5


def test_reliability_curve_bins_partition_counts() -> None:
    probs = [0.05, 0.15, 0.95]
    labels = [0, 0, 1]
    bins = reliability_curve(probs, labels, n_bins=10)
    assert sum(b.count for b in bins) == 3


def test_brier_score_bounds() -> None:
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert brier_score([0.0, 1.0], [1, 0]) == 1.0


# --- Bland-Altman -----------------------------------------------------------


def test_bland_altman_bias_and_loa() -> None:
    method = [61.0, 71.0, 81.0]
    reference = [60.0, 70.0, 80.0]  # method is +1 everywhere
    ba = bland_altman(method, reference)
    assert ba.bias == 1.0
    assert ba.mean_abs_error == 1.0
    assert ba.sd_diff == 0.0
    assert ba.loa_lower == 1.0 and ba.loa_upper == 1.0


def test_bland_altman_requires_pairs() -> None:
    with pytest.raises(ValueError, match="equal-length"):
        bland_altman([1.0, 2.0], [1.0])


# --- group held-out split ---------------------------------------------------


def test_group_holdout_split_holds_out_country() -> None:
    groups = ["NG", "NG", "ZA", "ZA"]
    train, test = group_holdout_split(groups, holdout={"ZA"})
    assert train == [0, 1]
    assert test == [2, 3]


# --- model card -------------------------------------------------------------


def test_triage_model_card_renders_sections() -> None:
    card = triage_model_card(version="v1", metrics={"diabetes": {"roc_auc": 0.74}})
    md = card.render_markdown()
    assert "# Model Card" in md
    assert "Intended use" in md
    assert "roc_auc = 0.740" in md
    assert "Limitations" in md
