"""DB-free capture-processing core: media file → rPPG → reply text + outcome.

This is the heart of the worker and deliberately knows nothing about the
database, WhatsApp, or the job queue — it takes a path to a downloaded video and
returns a :class:`CaptureResult`. That keeps it fully unit-testable (feed a
synthetic clip with an injected face detector) and lets the queue/runner layer
stay thin.

It reuses, never re-implements, the existing rPPG stack:
``extract_rgb_from_video`` (the WhatsApp-side equivalent of the browser sampler)
feeds ``run_rppg_pipeline`` (the shared CHROM/POS engine).
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from victus_api.core.logging import get_logger
from victus_api.toi.signal.pipeline import run_rppg_pipeline
from victus_api.toi.signal.video_extract import (
    FaceDetector,
    extract_rgb_from_video,
)
from victus_api.worker import messages

log = get_logger(__name__)


class CaptureOutcome(str, enum.Enum):
    """Terminal classification of a single capture attempt."""

    SUCCEEDED = "SUCCEEDED"  # vitals recovered — reply with results
    REJECTED = "REJECTED"    # capture unusable — ask user to re-record
    FAILED = "FAILED"        # unexpected error — retryable by the runner


@dataclass(frozen=True)
class CaptureResult:
    """What the processor hands back to the runner."""

    outcome: CaptureOutcome
    reply_text: str
    vitals: dict[str, Any] | None = None
    assessment_payload: dict[str, Any] | None = None
    pipeline_quality: str | None = None
    warnings: list[str] = field(default_factory=list)


def _fmt(value: float | None, suffix: str = "") -> str:
    return f"{value:g}{suffix}" if value is not None else "—"


def process_capture(
    media_path: str | Path,
    *,
    language: str | None = "en",
    skin_mask: bool = True,
    face_detector: FaceDetector | None = None,
    extractor: Callable[..., Any] = extract_rgb_from_video,
    pipeline: Callable[..., Any] = run_rppg_pipeline,
) -> CaptureResult:
    """Run the full video → vitals path and compose the user-facing reply.

    Parameters
    ----------
    media_path:
        Local path to the downloaded WhatsApp video.
    language:
        ``en`` / ``sn`` / ``nd`` — selects the reply copy.
    skin_mask, face_detector:
        Passed through to the extractor (tests inject a fixed-box detector).
    extractor, pipeline:
        Injection seams for testing; default to the production functions.

    Returns
    -------
    CaptureResult
        ``FAILED`` is raised only for *unexpected* errors and is the runner's
        signal to retry; ``REJECTED`` is a normal "please re-record" outcome.
    """
    try:
        extraction = extractor(
            media_path, skin_mask=skin_mask, face_detector=face_detector
        )
    except Exception:
        log.warning("capture_extract_failed", exc_info=True)
        return CaptureResult(
            outcome=CaptureOutcome.FAILED,
            reply_text=messages.error_message(language),
        )

    if not extraction.usable:
        log.info("capture_rejected_unusable", warnings=extraction.warnings)
        return CaptureResult(
            outcome=CaptureOutcome.REJECTED,
            reply_text=messages.rejected_message(language),
            warnings=list(extraction.warnings),
        )

    try:
        out = pipeline(**extraction.to_pipeline_kwargs())
    except Exception:
        log.warning("capture_pipeline_failed", exc_info=True)
        return CaptureResult(
            outcome=CaptureOutcome.FAILED,
            reply_text=messages.error_message(language),
        )

    if out.quality == "POOR":
        log.info("capture_rejected_poor_quality", warnings=list(out.warnings))
        return CaptureResult(
            outcome=CaptureOutcome.REJECTED,
            reply_text=messages.rejected_message(language),
            pipeline_quality=out.quality,
            warnings=list(out.warnings),
        )

    vitals: dict[str, Any] = {
        "heart_rate_bpm": out.heart_rate_bpm,
        "heart_rate_ci": list(out.heart_rate_ci) if out.heart_rate_ci else None,
        "respiratory_rate_bpm": out.respiratory_rate_bpm,
        "hrv_rmssd_ms": out.hrv_rmssd_ms,
        "hrv_sdnn_ms": out.hrv_sdnn_ms,
        "quality": out.quality,
        "method_selected": out.method_selected,
    }
    reply = messages.result_message(
        language,
        hr=_fmt(out.heart_rate_bpm),
        rr=_fmt(out.respiratory_rate_bpm),
        hrv=_fmt(out.hrv_rmssd_ms, " ms"),
    )
    log.info(
        "capture_succeeded",
        quality=out.quality,
        hr=out.heart_rate_bpm,
        method=out.method_selected,
    )
    return CaptureResult(
        outcome=CaptureOutcome.SUCCEEDED,
        reply_text=reply,
        vitals=vitals,
        assessment_payload=extraction.to_assessment_payload(),
        pipeline_quality=out.quality,
        warnings=list(out.warnings),
    )
