"""Unit tests for the experimental-biomarker gate (no DB, no HTTP)."""

from __future__ import annotations

import pytest

from victus_api.config import get_settings
from victus_api.toi.schemas import BiomarkerEstimate
from victus_api.toi.service import _visible_biomarkers


def _biomarkers() -> dict[str, BiomarkerEstimate]:
    return {
        "heart_rate": BiomarkerEstimate(value=72.0, unit="bpm"),
        "respiratory_rate": BiomarkerEstimate(value=16.0, unit="breaths/min"),
        "hrv_rmssd": BiomarkerEstimate(value=40.0, unit="ms", experimental=True),
        "stress_index": BiomarkerEstimate(value=42.0, unit="index", experimental=True),
    }


def test_experimental_biomarkers_hidden_by_default() -> None:
    get_settings.cache_clear()
    visible = _visible_biomarkers(_biomarkers())
    assert set(visible) == {"heart_rate", "respiratory_rate"}
    assert all(not v.experimental for v in visible.values())


def test_experimental_biomarkers_exposed_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOI_EXPOSE_EXPERIMENTAL_BIOMARKERS", "1")
    get_settings.cache_clear()
    try:
        visible = _visible_biomarkers(_biomarkers())
        assert set(visible) == {
            "heart_rate",
            "respiratory_rate",
            "hrv_rmssd",
            "stress_index",
        }
    finally:
        monkeypatch.delenv("TOI_EXPOSE_EXPERIMENTAL_BIOMARKERS", raising=False)
        get_settings.cache_clear()
