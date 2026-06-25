"""Unit tests for the predictive-task / anti-leakage contracts (no DB, no HTTP)."""

from __future__ import annotations

import pytest

from victus_api.triage.features import FEATURE_NAMES
from victus_api.triage.schemas import Disease
from victus_api.triage.tasks import (
    PREDICTIVE_TASKS,
    TaskKind,
    leakage_mask,
    mask_vector,
)


def _idx(name: str) -> int:
    return FEATURE_NAMES.index(name)


def test_every_disease_has_a_task() -> None:
    assert set(PREDICTIVE_TASKS) == set(Disease)


def test_obesity_forbids_bmi_defining_features() -> None:
    mask = leakage_mask(Disease.OBESITY)
    for forbidden in ("height_cm", "weight_kg", "bmi", "whtr"):
        assert mask[_idx(forbidden)] == 0.0
    # Waist is a legitimate proxy input and must remain available.
    assert mask[_idx("waist_cm")] == 1.0


def test_hypertension_forbids_bp_features() -> None:
    mask = leakage_mask(Disease.HYPERTENSION)
    for forbidden in ("systolic_bp", "diastolic_bp", "bp_mask", "pulse_pressure"):
        assert mask[_idx(forbidden)] == 0.0
    assert PREDICTIVE_TASKS[Disease.HYPERTENSION].kind is TaskKind.CONDITIONAL


def test_diabetes_is_a_clean_proxy_task() -> None:
    # The defining markers (HbA1c/FPG) are not features, so nothing is forbidden.
    assert PREDICTIVE_TASKS[Disease.DIABETES].forbidden_features == frozenset()
    assert all(m == 1.0 for m in leakage_mask(Disease.DIABETES))
    assert PREDICTIVE_TASKS[Disease.DIABETES].kind is TaskKind.PREDICTIVE


def test_mask_vector_zeroes_forbidden_and_preserves_allowed() -> None:
    vector = [1.0] * len(FEATURE_NAMES)
    masked = mask_vector(vector, Disease.OBESITY)
    assert masked[_idx("bmi")] == 0.0
    assert masked[_idx("weight_kg")] == 0.0
    assert masked[_idx("waist_cm")] == 1.0
    assert masked[_idx("age_years")] == 1.0


def test_mask_vector_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="feature vector length"):
        mask_vector([1.0, 2.0], Disease.DIABETES)
