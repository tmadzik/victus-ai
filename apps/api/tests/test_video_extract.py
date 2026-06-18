"""Unit test: video → RGB extractor feeds the rPPG pipeline correctly.

Synthesises a clip whose ROI carries a chrominance pulsation at a known heart
rate, runs it through ``extract_rgb_from_video`` and then ``run_rppg_pipeline``,
and asserts the recovered HR matches. This exercises the whole WhatsApp capture
path (decode → ROI sampling → time-series → CHROM/POS) without a real face on
camera, via an injected fixed-box detector.

No database or network — pure signal/IO. Requires the ``video`` extra (OpenCV).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2", reason="requires the 'video' extra (opencv)")

from victus_api.toi.signal.pipeline import run_rppg_pipeline  # noqa: E402
from victus_api.toi.signal.video_extract import (  # noqa: E402
    extract_rgb_from_video,
)

FPS = 30.0
DURATION_S = 12.0
HR_BPM = 72.0
SIZE = 240


def _write_pulsating_clip(path: Path, *, hr_bpm: float) -> bool:
    """Write a skin-toned clip whose channels pulsate at ``hr_bpm``.

    Green is modulated most, red less, blue least — mimicking the blood-volume
    chrominance signature CHROM/POS are built to extract (pure luminance flicker
    would be suppressed by design, so a chrominance-varying pulse is required).
    Returns False if no usable codec is available on this platform.
    """
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, (SIZE, SIZE))
    if not writer.isOpened():
        return False

    f_hz = hr_bpm / 60.0
    n_frames = int(DURATION_S * FPS)
    base_bgr = np.array([130.0, 150.0, 190.0])  # skin-ish (B, G, R)
    amp_bgr = np.array([2.0, 12.0, 6.0])         # G most, R less, B least
    for i in range(n_frames):
        t = i / FPS
        delta = amp_bgr * math.sin(2.0 * math.pi * f_hz * t)
        color = np.clip(base_bgr + delta, 0, 255)
        frame = np.empty((SIZE, SIZE, 3), dtype=np.uint8)
        frame[:, :] = color.astype(np.uint8)
        writer.write(frame)
    writer.release()
    return True


def test_extractor_recovers_known_heart_rate(tmp_path: Path) -> None:
    clip = tmp_path / "pulse.mp4"
    if not _write_pulsating_clip(clip, hr_bpm=HR_BPM):
        pytest.skip("no OpenCV video codec available to author the test clip")

    # Whole-frame face box → forehead/malar ROIs all land on pulsating skin.
    fixed_box = (0, 0, SIZE, SIZE)
    extraction = extract_rgb_from_video(
        clip,
        skin_mask=False,  # synthetic flat color; skin masking tested on real clips
        face_detector=lambda _frame: fixed_box,
        redetect_every=1,
    )

    assert extraction.usable
    assert extraction.face_presence_ratio == pytest.approx(1.0, abs=0.05)
    assert extraction.frames_with_face >= int(DURATION_S * FPS) - 2
    assert extraction.rgb_samples.shape[1] == 3
    # Channels actually vary (the pulsation survived encode/decode).
    assert extraction.rgb_samples[:, 1].std() > 0.5

    out = run_rppg_pipeline(**extraction.to_pipeline_kwargs())

    assert out.quality in {"GOOD", "DEGRADED"}
    assert out.heart_rate_bpm is not None
    # CHROM/POS HR recovery within a few bpm of the injected 72 bpm.
    assert out.heart_rate_bpm == pytest.approx(HR_BPM, abs=5.0)


def test_low_face_presence_is_unusable(tmp_path: Path) -> None:
    clip = tmp_path / "noface.mp4"
    if not _write_pulsating_clip(clip, hr_bpm=HR_BPM):
        pytest.skip("no OpenCV video codec available to author the test clip")

    # Detector never finds a face → extraction should be flagged unusable.
    extraction = extract_rgb_from_video(
        clip, face_detector=lambda _frame: None
    )
    assert not extraction.usable
    assert "insufficient_face_presence" in extraction.warnings


def test_assessment_payload_matches_toi_contract(tmp_path: Path) -> None:
    clip = tmp_path / "pulse.mp4"
    if not _write_pulsating_clip(clip, hr_bpm=HR_BPM):
        pytest.skip("no OpenCV video codec available to author the test clip")

    extraction = extract_rgb_from_video(
        clip, skin_mask=False, face_detector=lambda _frame: (0, 0, SIZE, SIZE)
    )
    payload = extraction.to_assessment_payload()

    assert set(payload) == {
        "frames",
        "sample_rate_hz",
        "duration_s",
        "motion_score",
        "lighting_score",
        "face_presence_ratio",
    }
    first = payload["frames"][0]
    assert set(first) == {"t_ms", "r", "g", "b"}
    assert isinstance(first["t_ms"], int)
    assert 0.0 <= first["r"] <= 255.0
