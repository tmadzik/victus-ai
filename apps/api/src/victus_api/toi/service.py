"""Pathway B orchestration: pipeline → persist → audit."""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    User,
)
from victus_api.db.models import (
    FitzpatrickScale as DbFitzpatrick,
)
from victus_api.db.models import (
    ToiAssessment as ToiAssessmentRow,
)
from victus_api.db.models import (
    ToiQuality as DbToiQuality,
)
from victus_api.toi.schemas import (
    BiomarkerEstimate,
    SignalQuality,
    ToiAssessmentRequest,
    ToiAssessmentResponse,
    ToiQuality,
)
from victus_api.toi.signal.pipeline import PipelineOutput, run_rppg_pipeline

log = get_logger(__name__)


NEXT_ACTION: dict[ToiQuality, str] = {
    ToiQuality.GOOD: "review_and_continue",
    ToiQuality.DEGRADED: "consider_recapture",
    ToiQuality.POOR: "recapture_required",
}


async def assess_toi(
    db: AsyncSession,
    *,
    user: User,
    payload: ToiAssessmentRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> ToiAssessmentResponse:
    timestamps = np.array(
        [f.t_ms for f in payload.frames], dtype=np.float64
    ) / 1000.0
    rgb = np.array(
        [[f.r, f.g, f.b] for f in payload.frames], dtype=np.float64
    )

    pipeline = run_rppg_pipeline(
        timestamps_seconds=timestamps,
        rgb_samples=rgb,
        nominal_sample_rate_hz=payload.sample_rate_hz,
        motion_score=payload.motion_score,
        lighting_score_client=payload.lighting_score,
        face_presence_ratio=payload.face_presence_ratio,
    )

    biomarkers_dto = _build_biomarker_dto(pipeline)
    signal_quality = SignalQuality(
        snr_chrom_db=pipeline.snr_chrom_db,
        snr_pos_db=pipeline.snr_pos_db,
        method_selected=pipeline.method_selected,  # type: ignore[arg-type]
        motion_score=pipeline.motion_score,
        lighting_score=pipeline.lighting_score,
        face_presence_ratio=pipeline.face_presence_ratio,
        frames_used=pipeline.frames_used,
    )

    quality_enum = ToiQuality(pipeline.quality)
    row = ToiAssessmentRow(
        user_id=user.id,
        quality=DbToiQuality(quality_enum.value),
        duration_s=pipeline.duration_s,
        sample_rate_hz=pipeline.sample_rate_hz,
        frame_count=pipeline.frame_count,
        frames_used=pipeline.frames_used,
        skin_tone_estimate=(
            DbFitzpatrick(payload.skin_tone_estimate.value)
            if payload.skin_tone_estimate is not None
            else None
        ),
        method_selected=pipeline.method_selected,
        snr_chrom_db=pipeline.snr_chrom_db,
        snr_pos_db=pipeline.snr_pos_db,
        motion_score=pipeline.motion_score,
        lighting_score=pipeline.lighting_score,
        face_presence_ratio=pipeline.face_presence_ratio,
        heart_rate_bpm=pipeline.heart_rate_bpm,
        heart_rate_ci_low=pipeline.heart_rate_ci[0]
        if pipeline.heart_rate_ci is not None
        else None,
        heart_rate_ci_high=pipeline.heart_rate_ci[1]
        if pipeline.heart_rate_ci is not None
        else None,
        respiratory_rate_bpm=pipeline.respiratory_rate_bpm,
        respiratory_rate_ci_low=pipeline.respiratory_rate_ci[0]
        if pipeline.respiratory_rate_ci is not None
        else None,
        respiratory_rate_ci_high=pipeline.respiratory_rate_ci[1]
        if pipeline.respiratory_rate_ci is not None
        else None,
        hrv_rmssd_ms=pipeline.hrv_rmssd_ms,
        hrv_sdnn_ms=pipeline.hrv_sdnn_ms,
        stress_index=pipeline.stress_index,
        biomarkers={k: v.model_dump() for k, v in biomarkers_dto.items()},
        signal_quality=signal_quality.model_dump(),
        warnings=list(pipeline.warnings),
        pipeline_version=pipeline.pipeline_version,
    )
    db.add(row)
    await db.flush()

    metadata: dict[str, Any] = {
        "assessment_id": str(row.id),
        "quality": quality_enum.value,
        "method_selected": pipeline.method_selected,
        "snr_db": round(
            max(pipeline.snr_chrom_db, pipeline.snr_pos_db), 3
        ),
        "frames_used": pipeline.frames_used,
        "pipeline_version": pipeline.pipeline_version,
        "warnings": list(pipeline.warnings),
    }
    if pipeline.heart_rate_bpm is not None:
        metadata["heart_rate_bpm"] = pipeline.heart_rate_bpm

    if quality_enum == ToiQuality.POOR:
        await write_audit(
            db,
            action=AuditAction.PATHWAY_B_QUALITY_REJECTED,
            actor_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource=f"toi:assessment:{row.id}",
            metadata=metadata,
        )
    else:
        await write_audit(
            db,
            action=AuditAction.PATHWAY_B_ASSESSMENT_COMPLETED,
            actor_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource=f"toi:assessment:{row.id}",
            metadata=metadata,
        )

    log.info(
        "toi_assessment_completed",
        assessment_id=str(row.id),
        quality=quality_enum.value,
        method=pipeline.method_selected,
        snr_chrom_db=pipeline.snr_chrom_db,
        snr_pos_db=pipeline.snr_pos_db,
        hr_bpm=pipeline.heart_rate_bpm,
    )

    return _to_response(
        row=row,
        biomarkers=biomarkers_dto,
        signal_quality=signal_quality,
        pipeline=pipeline,
    )


async def list_assessments_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 25,
) -> list[ToiAssessmentResponse]:
    stmt = (
        select(ToiAssessmentRow)
        .where(ToiAssessmentRow.user_id == user_id)
        .order_by(desc(ToiAssessmentRow.created_at))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    return [_row_to_response(r) for r in rows]


# --- Helpers -----------------------------------------------------------------


def _build_biomarker_dto(
    pipeline: PipelineOutput,
) -> dict[str, BiomarkerEstimate]:
    out: dict[str, BiomarkerEstimate] = {}
    if pipeline.heart_rate_bpm is not None:
        out["heart_rate"] = BiomarkerEstimate(
            value=pipeline.heart_rate_bpm,
            ci_low=pipeline.heart_rate_ci[0]
            if pipeline.heart_rate_ci is not None
            else None,
            ci_high=pipeline.heart_rate_ci[1]
            if pipeline.heart_rate_ci is not None
            else None,
            unit="bpm",
        )
    if pipeline.respiratory_rate_bpm is not None:
        out["respiratory_rate"] = BiomarkerEstimate(
            value=pipeline.respiratory_rate_bpm,
            ci_low=pipeline.respiratory_rate_ci[0]
            if pipeline.respiratory_rate_ci is not None
            else None,
            ci_high=pipeline.respiratory_rate_ci[1]
            if pipeline.respiratory_rate_ci is not None
            else None,
            unit="breaths/min",
        )
    if pipeline.hrv_rmssd_ms is not None:
        out["hrv_rmssd"] = BiomarkerEstimate(
            value=pipeline.hrv_rmssd_ms, unit="ms"
        )
    if pipeline.hrv_sdnn_ms is not None:
        out["hrv_sdnn"] = BiomarkerEstimate(
            value=pipeline.hrv_sdnn_ms, unit="ms"
        )
    if pipeline.stress_index is not None:
        out["stress_index"] = BiomarkerEstimate(
            value=pipeline.stress_index, unit="index", ci_low=0.0, ci_high=100.0
        )
    return out


def _to_response(
    *,
    row: ToiAssessmentRow,
    biomarkers: dict[str, BiomarkerEstimate],
    signal_quality: SignalQuality,
    pipeline: PipelineOutput,
) -> ToiAssessmentResponse:
    quality_enum = ToiQuality(row.quality.value)
    return ToiAssessmentResponse(
        id=row.id,
        quality=quality_enum,
        duration_s=pipeline.duration_s,
        sample_rate_hz=pipeline.sample_rate_hz,
        frame_count=pipeline.frame_count,
        biomarkers=biomarkers,
        signal_quality=signal_quality,
        method_details=pipeline.method_details,
        warnings=list(pipeline.warnings),
        next_action=NEXT_ACTION[quality_enum],
        pipeline_version=pipeline.pipeline_version,
        created_at=row.created_at,
    )


def _row_to_response(row: ToiAssessmentRow) -> ToiAssessmentResponse:
    biomarkers: dict[str, BiomarkerEstimate] = {}
    for k, v in row.biomarkers.items():
        if isinstance(v, dict):
            biomarkers[k] = BiomarkerEstimate.model_validate(v)
    quality_enum = ToiQuality(row.quality.value)
    sq_data = row.signal_quality if isinstance(row.signal_quality, dict) else {}
    return ToiAssessmentResponse(
        id=row.id,
        quality=quality_enum,
        duration_s=row.duration_s,
        sample_rate_hz=row.sample_rate_hz,
        frame_count=row.frame_count,
        biomarkers=biomarkers,
        signal_quality=SignalQuality.model_validate(
            {
                "snr_chrom_db": sq_data.get("snr_chrom_db", row.snr_chrom_db),
                "snr_pos_db": sq_data.get("snr_pos_db", row.snr_pos_db),
                "method_selected": sq_data.get(
                    "method_selected", row.method_selected
                ),
                "motion_score": sq_data.get("motion_score", row.motion_score),
                "lighting_score": sq_data.get(
                    "lighting_score", row.lighting_score
                ),
                "face_presence_ratio": sq_data.get(
                    "face_presence_ratio", row.face_presence_ratio
                ),
                "frames_used": sq_data.get("frames_used", row.frames_used),
            }
        ),
        method_details={},
        warnings=list(row.warnings),
        next_action=NEXT_ACTION[quality_enum],
        pipeline_version=row.pipeline_version,
        created_at=row.created_at,
    )
