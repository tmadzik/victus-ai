"""Pathway B corrector: the learned calibration must measurably hold.

These are deterministic (fixed seed) and fast — a few hundred synthetic pairs,
a short fit — so they run in CI without the ml job ballooning.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from victus_api.training.toi_corrector import (
    FEATURE_NAMES,
    TARGET_NAMES,
    evaluate_corrector,
    rows_to_matrix,
    save_corrector_checkpoint,
    split_rows,
    synthesize_calibration_corpus,
    train_corrector,
)


def _fit_eval(n: int = 1200, seed: int = 7):
    rows = rows_to_matrix(synthesize_calibration_corpus(n, seed=seed))
    train, val = split_rows(rows, val_frac=0.2, seed=seed)
    result = train_corrector(train, epochs=150, seed=seed)
    return result, val, evaluate_corrector(result, val)


def test_correction_reduces_overall_hr_error() -> None:
    _, _, report = _fit_eval()
    overall = report["overall"]
    # The corrector must cut held-out HR error and remove the systematic bias.
    assert overall["corrected_mae_bpm"] < overall["raw_mae_bpm"]
    assert abs(overall["corrected_bias_bpm"]) < abs(overall["raw_bias_bpm"])


def test_correction_closes_the_dark_skin_gap() -> None:
    """The headline fairness claim: V–VI bias is the worst raw and must collapse."""
    _, _, report = _fit_eval()
    v_vi = report["by_skin_tone"]["V_VI"]
    assert v_vi["raw_bias_bpm"] > 3.0  # synthetic data really does inject the gap
    assert abs(v_vi["corrected_bias_bpm"]) < abs(v_vi["raw_bias_bpm"]) / 2.0
    assert v_vi["corrected_mae_bpm"] < v_vi["raw_mae_bpm"]


def test_rows_to_matrix_handles_absent_optional_fields() -> None:
    rows = rows_to_matrix(
        [
            {
                "rppg_hr_bpm": 80.0,
                "rppg_rr_bpm": None,  # absent input → imputed
                "rppg_hrv_rmssd_ms": None,
                "rppg_hrv_sdnn_ms": None,
                "snr_chrom_db": 6.0,
                "snr_pos_db": 7.0,
                "method_selected": "pos",
                "skin_tone": "V",
                "reference_hr_bpm": 76.0,
                "reference_rr_bpm": None,  # absent target → NaN (masked in loss)
                "reference_hrv_rmssd_ms": None,
                "reference_hrv_sdnn_ms": None,
            }
        ]
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.features.shape == (len(FEATURE_NAMES),)
    assert row.targets.shape == (len(TARGET_NAMES),)
    assert not np.isnan(row.features).any()  # inputs are always concrete
    assert not np.isnan(row.targets[0])  # HR truth present
    assert np.isnan(row.targets[1])  # RR truth absent → NaN sentinel
    assert row.features[6] == 1.0  # method_is_pos
    assert row.features[7] == 5.0  # Fitzpatrick V → ordinal 5


def test_checkpoint_roundtrip_writes_meta(tmp_path: Path) -> None:
    result, _, report = _fit_eval(n=400)
    out = tmp_path / "toi_corrector_v1.pt"
    save_corrector_checkpoint(
        result, out, version="9.9.9", validation=report, n_train=320, n_val=80
    )
    assert out.exists()
    meta = json.loads(out.with_suffix(out.suffix + ".meta.json").read_text())
    assert meta["model_kind"] == "toi_corrector_v1"
    assert meta["version"] == "9.9.9"
    assert meta["feature_names"] == list(FEATURE_NAMES)
    assert meta["target_names"] == list(TARGET_NAMES)
    assert meta["validation"]["overall"]["n"] > 0
