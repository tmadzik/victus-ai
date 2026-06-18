"""Unit tests for the DB-free worker core (``process_capture``).

Reuses the synthetic-clip authoring from the extractor test to drive the full
video → vitals → reply path with an injected fixed-box detector. No DB, no
WhatsApp — just the processing core and message composition.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2", reason="requires the 'video' extra (opencv)")

from victus_api.worker import messages  # noqa: E402
from victus_api.worker.processor import (  # noqa: E402
    CaptureOutcome,
    process_capture,
)

FPS = 30.0
DURATION_S = 12.0
SIZE = 240
WHOLE_FRAME = (0, 0, SIZE, SIZE)


def _write_clip(path: Path, *, hr_bpm: float, pulsate: bool = True) -> bool:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, (SIZE, SIZE))
    if not writer.isOpened():
        return False
    import numpy as np

    f_hz = hr_bpm / 60.0
    base = np.array([130.0, 150.0, 190.0])
    amp = np.array([2.0, 12.0, 6.0]) if pulsate else np.zeros(3)
    for i in range(int(DURATION_S * FPS)):
        t = i / FPS
        col = np.clip(base + amp * math.sin(2 * math.pi * f_hz * t), 0, 255)
        frame = np.empty((SIZE, SIZE, 3), np.uint8)
        frame[:, :] = col.astype(np.uint8)
        writer.write(frame)
    writer.release()
    return True


def test_process_capture_success(tmp_path: Path) -> None:
    clip = tmp_path / "pulse.mp4"
    if not _write_clip(clip, hr_bpm=72.0):
        pytest.skip("no OpenCV codec to author test clip")

    res = process_capture(
        clip,
        language="en",
        skin_mask=False,
        face_detector=lambda _f: WHOLE_FRAME,
    )

    assert res.outcome is CaptureOutcome.SUCCEEDED
    assert res.vitals is not None
    assert res.vitals["heart_rate_bpm"] == pytest.approx(72.0, abs=5.0)
    # Reply carries vitals and the non-diagnosis disclaimer.
    assert "bpm" in res.reply_text
    assert "not a medical diagnosis" in res.reply_text.lower()
    # The assessment payload is ready to POST to the existing /toi endpoint.
    assert res.assessment_payload is not None
    assert "frames" in res.assessment_payload


def test_process_capture_rejected_when_no_face(tmp_path: Path) -> None:
    clip = tmp_path / "noface.mp4"
    if not _write_clip(clip, hr_bpm=72.0):
        pytest.skip("no OpenCV codec to author test clip")

    res = process_capture(
        clip, language="en", face_detector=lambda _f: None
    )
    assert res.outcome is CaptureOutcome.REJECTED
    assert res.vitals is None
    assert "re-record" in res.reply_text.lower()


def test_process_capture_failed_on_bad_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.mp4"
    res = process_capture(missing, language="en")
    assert res.outcome is CaptureOutcome.FAILED
    assert res.reply_text == messages.error_message("en")


def test_localized_reply_selected(tmp_path: Path) -> None:
    clip = tmp_path / "pulse.mp4"
    if not _write_clip(clip, hr_bpm=72.0):
        pytest.skip("no OpenCV codec to author test clip")

    res = process_capture(
        clip, language="sn", skin_mask=False, face_detector=lambda _f: WHOLE_FRAME
    )
    assert res.outcome is CaptureOutcome.SUCCEEDED
    # Shona result copy, not English.
    assert "Ongororo" in res.reply_text


def test_unknown_language_falls_back_to_english() -> None:
    assert messages.result_message("xx", hr="70", rr="15", hrv="40 ms") == (
        messages.result_message("en", hr="70", rr="15", hrv="40 ms")
    )
