"""Env-gated TOI corrector: off by default, and when on it pulls an inflated
dark-skin heart rate back toward truth and marks its provenance.

Self-contained: trains a tiny corrector to a tmp checkpoint (the .pt binary is
not committed), so it runs in CI under the ml extra without external artifacts.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from victus_api.toi.corrector import get_corrector
from victus_api.toi.schemas import FitzpatrickScale
from victus_api.toi.service import _maybe_apply_corrector
from victus_api.toi.signal.pipeline import PipelineOutput
from victus_api.training.toi_corrector import (
    rows_to_matrix,
    save_corrector_checkpoint,
    synthesize_calibration_corpus,
    train_corrector,
)


def _fake_pipeline(*, hr: float, quality: str = "GOOD") -> PipelineOutput:
    return PipelineOutput(
        quality=quality,
        method_selected="pos",
        duration_s=20.0,
        sample_rate_hz=30.0,
        frame_count=600,
        frames_used=580,
        snr_chrom_db=1.5,
        snr_pos_db=3.5,
        motion_score=0.9,
        lighting_score=0.8,
        face_presence_ratio=0.95,
        heart_rate_bpm=hr,
        heart_rate_ci=(hr - 3.0, hr + 3.0),
        respiratory_rate_bpm=16.0,
        respiratory_rate_ci=(14.0, 18.0),
        hrv_rmssd_ms=40.0,
        hrv_sdnn_ms=55.0,
        stress_index=42.0,
        warnings=[],
        method_details={"method": "pos"},
        pipeline_version="rppg-1",
    )


@pytest.fixture()
def trained_checkpoint(tmp_path: Path) -> Path:
    rows = rows_to_matrix(synthesize_calibration_corpus(1000, seed=5))
    result = train_corrector(rows, epochs=150, seed=5)
    out = tmp_path / "toi_corrector_v1.pt"
    save_corrector_checkpoint(
        result, out, version="test", validation={}, n_train=len(rows), n_val=0
    )
    return out


def test_corrector_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VICTUS_TOI_CORRECTOR_PATH", raising=False)
    get_corrector.cache_clear()
    assert get_corrector() is None
    # And the service helper is a clean no-op.
    pipe = _fake_pipeline(hr=88.0)
    payload = SimpleNamespace(skin_tone_estimate=FitzpatrickScale.VI)
    assert _maybe_apply_corrector(pipe, payload) is pipe  # type: ignore[arg-type]


def test_corrector_pulls_dark_skin_hr_toward_truth(
    monkeypatch: pytest.MonkeyPatch, trained_checkpoint: Path
) -> None:
    monkeypatch.setenv("VICTUS_TOI_CORRECTOR_PATH", str(trained_checkpoint))
    get_corrector.cache_clear()
    corrector = get_corrector()
    assert corrector is not None

    # Raw rPPG over-reads HR on Fitzpatrick VI; the corrector should reduce it.
    pipe = _fake_pipeline(hr=92.0)
    corrected = corrector.correct(pipe, FitzpatrickScale.VI)
    assert corrected.heart_rate_ci is not None
    assert corrected.heart_rate_bpm < pipe.heart_rate_bpm
    get_corrector.cache_clear()


def test_corrector_marks_provenance_and_skips_poor(
    monkeypatch: pytest.MonkeyPatch, trained_checkpoint: Path
) -> None:
    monkeypatch.setenv("VICTUS_TOI_CORRECTOR_PATH", str(trained_checkpoint))
    get_corrector.cache_clear()
    payload = SimpleNamespace(skin_tone_estimate=FitzpatrickScale.V)

    good = _maybe_apply_corrector(_fake_pipeline(hr=90.0), payload)  # type: ignore[arg-type]
    assert good.method_details["corrector"]["applied"] is True
    assert good.method_details["corrector"]["raw_heart_rate_bpm"] == 90.0

    # POOR captures are never "corrected".
    poor = _fake_pipeline(hr=90.0, quality="POOR")
    assert _maybe_apply_corrector(poor, payload) is poor  # type: ignore[arg-type]
    get_corrector.cache_clear()
