"""Pathway B — env-gated rPPG biomarker corrector (inference).

When ``VICTUS_TOI_CORRECTOR_PATH`` points at a ``toi_corrector_v1`` checkpoint,
the trained residual corrector (see :mod:`victus_api.training.toi_corrector`)
nudges the raw CHROM/POS biomarkers toward reference-device truth and narrows the
documented skin-tone gap, attaching a per-target predictive interval.

Off by default: with the env unset, or the file missing, or torch absent (the
cPanel build ships without it), :func:`get_corrector` returns ``None`` and the
service serves the raw pipeline output unchanged. The torch import is lazy for
exactly that reason — importing this module never pulls in torch.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from victus_api.core.logging import get_logger
from victus_api.toi.signal.pipeline import PipelineOutput

log = get_logger("victus_api.toi.corrector")

# Index of each target in the corrector's output vector (see toi_corrector).
_HR, _RR, _RMSSD, _SDNN = 0, 1, 2, 3
_CI_Z = 1.96  # ~95% interval from the predictive σ


@dataclass(frozen=True, slots=True)
class CorrectedBiomarkers:
    """Corrected biomarkers; each field falls back to the pipeline's original
    when that target was absent (so it is safe to splat over the pipeline)."""

    heart_rate_bpm: float | None
    heart_rate_ci: tuple[float, float] | None
    respiratory_rate_bpm: float | None
    respiratory_rate_ci: tuple[float, float] | None
    hrv_rmssd_ms: float | None
    hrv_sdnn_ms: float | None
    model_kind: str
    model_version: str


class ToiCorrector:
    """Loads a corrector checkpoint and applies it to a :class:`PipelineOutput`."""

    def __init__(self, path: Path) -> None:
        import torch  # lazy — keeps the torch-free build importable

        from victus_api.training.toi_corrector import (
            FEATURE_NAMES,
            FITZPATRICK_ORDINAL,
            TARGET_NAMES,
            FeatureScaler,
            ToiCorrectorNet,
        )

        meta_path = path.with_suffix(path.suffix + ".meta.json")
        meta = json.loads(meta_path.read_text())
        hidden = int(meta["hidden"])
        self._fitz = FITZPATRICK_ORDINAL
        self.model_kind: str = str(meta["model_kind"])
        self.model_version: str = str(meta.get("version", "unknown"))

        model = ToiCorrectorNet(len(FEATURE_NAMES), len(TARGET_NAMES), hidden=hidden)
        model.load_state_dict(torch.load(path, map_location="cpu"))
        model.eval()
        self._model = model
        self._predict = _make_predictor(model, torch)
        self._scaler = FeatureScaler(
            mean=np.asarray(meta["scaler"]["mean"], dtype=np.float32),
            std=np.asarray(meta["scaler"]["std"], dtype=np.float32),
        )

    def correct(
        self, pipeline: PipelineOutput, skin_tone: object | None
    ) -> CorrectedBiomarkers:
        """Return corrected biomarkers for the present targets.

        Absent optional inputs (RR / HRV the pipeline did not recover) are imputed
        with the training-set mean so the feature vector is complete; the
        corresponding *output* is only used when the pipeline actually produced
        that biomarker, so a guessed input never becomes a reported value.
        """
        mean = self._scaler.mean
        rppg_hr = float(pipeline.heart_rate_bpm or mean[0])
        rppg_rr = (
            float(pipeline.respiratory_rate_bpm)
            if pipeline.respiratory_rate_bpm is not None
            else float(mean[1])
        )
        rppg_rmssd = (
            float(pipeline.hrv_rmssd_ms)
            if pipeline.hrv_rmssd_ms is not None
            else float(mean[2])
        )
        rppg_sdnn = (
            float(pipeline.hrv_sdnn_ms)
            if pipeline.hrv_sdnn_ms is not None
            else float(mean[3])
        )
        tone = getattr(skin_tone, "value", skin_tone)
        fitz_ord = float(self._fitz.get(str(tone), 0)) if tone is not None else 0.0
        method_is_pos = 1.0 if pipeline.method_selected == "pos" else 0.0

        features = np.array(
            [
                rppg_hr,
                rppg_rr,
                rppg_rmssd,
                rppg_sdnn,
                float(pipeline.snr_chrom_db),
                float(pipeline.snr_pos_db),
                method_is_pos,
                fitz_ord,
            ],
            dtype=np.float32,
        )
        corrected, sigma = self._predict(
            self._scaler.transform(features[None, :]),
            features[None, [0, 1, 2, 3]],
        )
        corrected = corrected[0]
        sigma = sigma[0]

        hr = round(float(corrected[_HR]), 1)
        hr_ci = (
            round(hr - _CI_Z * float(sigma[_HR]), 1),
            round(hr + _CI_Z * float(sigma[_HR]), 1),
        )
        rr = (
            round(float(corrected[_RR]), 1)
            if pipeline.respiratory_rate_bpm is not None
            else None
        )
        rr_ci = (
            (
                round(rr - _CI_Z * float(sigma[_RR]), 1),
                round(rr + _CI_Z * float(sigma[_RR]), 1),
            )
            if rr is not None
            else None
        )
        rmssd = (
            round(float(corrected[_RMSSD]), 1)
            if pipeline.hrv_rmssd_ms is not None
            else None
        )
        sdnn = (
            round(float(corrected[_SDNN]), 1)
            if pipeline.hrv_sdnn_ms is not None
            else None
        )
        return CorrectedBiomarkers(
            heart_rate_bpm=hr,
            heart_rate_ci=hr_ci,
            respiratory_rate_bpm=rr,
            respiratory_rate_ci=rr_ci,
            hrv_rmssd_ms=rmssd,
            hrv_sdnn_ms=sdnn,
            model_kind=self.model_kind,
            model_version=self.model_version,
        )


def _make_predictor(model: object, torch: object):  # noqa: ANN202
    """Bind a no-grad numpy→numpy predictor over the loaded torch model."""

    @torch.no_grad()  # type: ignore[attr-defined]
    def _predict(x_scaled: np.ndarray, base: np.ndarray):  # noqa: ANN202
        mean, log_var = model(  # type: ignore[operator]
            torch.from_numpy(x_scaled),  # type: ignore[attr-defined]
            torch.from_numpy(base),  # type: ignore[attr-defined]
        )
        sigma = torch.exp(0.5 * log_var)  # type: ignore[attr-defined]
        return mean.numpy(), sigma.numpy()

    return _predict


@lru_cache(maxsize=1)
def get_corrector() -> ToiCorrector | None:
    """Return the configured corrector, or ``None`` to serve the raw pipeline."""
    path_str = os.environ.get("VICTUS_TOI_CORRECTOR_PATH")
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_file():
        log.warning("toi_corrector_path_missing", path=str(path))
        return None
    try:
        corrector = ToiCorrector(path)
    except Exception:
        log.exception("toi_corrector_load_failed", path=str(path))
        return None
    log.info("toi_corrector_loaded", path=str(path), kind=corrector.model_kind)
    return corrector
