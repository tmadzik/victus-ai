"""Calibration domain service — record, list, stats."""

from __future__ import annotations

import csv
import uuid
from collections.abc import AsyncIterator
from io import StringIO

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from victus_api.audit.service import write_audit
from victus_api.calibration import CALIBRATION_VERSION
from victus_api.calibration.schemas import (
    CalibrationRecordResponse,
    CalibrationStatsBlock,
    CalibrationStatsResponse,
    HrvCalibrationStatsBlock,
    RecordCalibrationRequest,
    ReferenceDeviceType,
)
from victus_api.calibration.statistics import (
    CalibrationPair,
    CalibrationStats,
    HrvCalibrationStats,
    compute_stratified,
    rmssd_from_rr_intervals,
    sdnn_from_rr_intervals,
)
from victus_api.core.exceptions import NotFoundError, VictusError
from victus_api.core.logging import get_logger
from victus_api.db.models import (
    AuditAction,
    RppgCalibrationRecord,
    StudySession,
    ToiAssessment,
    User,
)
from victus_api.db.models import (
    FitzpatrickScale as DbFitzpatrick,
)
from victus_api.db.models import (
    ReferenceDeviceType as DbReferenceDeviceType,
)
from victus_api.study.service import lock_session_if_needed
from victus_api.toi.schemas import FitzpatrickScale, ToiQuality

log = get_logger(__name__)


class CalibrationConflictError(VictusError):
    status_code = 409
    error_code = "calibration_pair_exists"


async def record_calibration_pair(
    db: AsyncSession,
    *,
    user: User,
    payload: RecordCalibrationRequest,
    ip_address: str | None,
    user_agent: str | None,
) -> CalibrationRecordResponse:
    stmt = select(ToiAssessment).where(
        ToiAssessment.id == payload.toi_assessment_id,
        ToiAssessment.user_id == user.id,
    )
    assessment = (await db.execute(stmt)).scalar_one_or_none()
    if assessment is None:
        raise NotFoundError("TOI assessment not found for this user.")
    if assessment.heart_rate_bpm is None:
        raise VictusError(
            "This assessment did not produce a heart rate (likely POOR quality); "
            "cannot pair to a reference reading.",
            details={"toi_assessment_id": str(payload.toi_assessment_id)},
        )

    existing = (
        await db.execute(
            select(RppgCalibrationRecord).where(
                RppgCalibrationRecord.toi_assessment_id == payload.toi_assessment_id,
                RppgCalibrationRecord.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise CalibrationConflictError(
            "This assessment has already been paired to a reference reading.",
            details={"existing_calibration_id": str(existing.id)},
        )

    # Look up the researcher's active session (if any) so we can attach the
    # capture to it AND inherit the subject's Fitzpatrick estimate when no
    # explicit value was provided.
    active_session = (
        await db.execute(
            select(StudySession).where(
                StudySession.user_id == user.id,
                StudySession.ended_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    skin_tone: DbFitzpatrick | None
    if payload.skin_tone_estimate is not None:
        skin_tone = DbFitzpatrick(payload.skin_tone_estimate.value)
    elif assessment.skin_tone_estimate is not None:
        skin_tone = assessment.skin_tone_estimate
    elif (
        active_session is not None
        and active_session.subject.fitzpatrick_scale is not None
    ):
        skin_tone = active_session.subject.fitzpatrick_scale
    else:
        skin_tone = None

    # Reference HRV is computed server-side from the raw RR intervals (if
    # provided) — the persisted value is canonical so any future bug fix to
    # the RMSSD/SDNN formula propagates without rerunning study captures.
    reference_rmssd: float | None = None
    reference_sdnn: float | None = None
    if payload.reference_rr_intervals_ms:
        reference_rmssd = rmssd_from_rr_intervals(payload.reference_rr_intervals_ms)
        reference_sdnn = sdnn_from_rr_intervals(payload.reference_rr_intervals_ms)
        if reference_rmssd is not None:
            reference_rmssd = round(reference_rmssd, 3)
        if reference_sdnn is not None:
            reference_sdnn = round(reference_sdnn, 3)

    row = RppgCalibrationRecord(
        user_id=user.id,
        toi_assessment_id=assessment.id,
        reference_device_type=DbReferenceDeviceType(
            payload.reference_device_type.value
        ),
        reference_device_label=payload.reference_device_label,
        reference_hr_bpm=payload.reference_hr_bpm,
        reference_rr_bpm=payload.reference_rr_bpm,
        reference_hr_sample_count=payload.reference_hr_sample_count,
        reference_hrv_rmssd_ms=reference_rmssd,
        reference_hrv_sdnn_ms=reference_sdnn,
        reference_rr_intervals_ms=(
            payload.reference_rr_intervals_ms
            if payload.reference_rr_intervals_ms
            else None
        ),
        auto_paired_from_ble=payload.auto_paired_from_ble,
        rppg_hr_bpm=assessment.heart_rate_bpm,
        rppg_rr_bpm=assessment.respiratory_rate_bpm,
        rppg_hrv_rmssd_ms=assessment.hrv_rmssd_ms,
        rppg_hrv_sdnn_ms=assessment.hrv_sdnn_ms,
        rppg_quality=assessment.quality.value,
        rppg_method_selected=assessment.method_selected,
        rppg_snr_chrom_db=assessment.snr_chrom_db,
        rppg_snr_pos_db=assessment.snr_pos_db,
        rppg_pipeline_version=assessment.pipeline_version,
        skin_tone_estimate=skin_tone,
        notes=payload.notes,
        study_session_id=active_session.id if active_session is not None else None,
    )
    db.add(row)
    await db.flush()

    if active_session is not None:
        await lock_session_if_needed(
            db,
            session=active_session,
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    metadata = {
        "calibration_id": str(row.id),
        "toi_assessment_id": str(assessment.id),
        "reference_device_type": payload.reference_device_type.value,
        "reference_hr_bpm": payload.reference_hr_bpm,
        "rppg_hr_bpm": assessment.heart_rate_bpm,
        "error_bpm": round(
            assessment.heart_rate_bpm - payload.reference_hr_bpm, 3
        ),
        "auto_paired_from_ble": payload.auto_paired_from_ble,
    }
    if reference_rmssd is not None and assessment.hrv_rmssd_ms is not None:
        metadata["rmssd_error_ms"] = round(
            assessment.hrv_rmssd_ms - reference_rmssd, 3
        )
    if active_session is not None:
        metadata["study_session_id"] = str(active_session.id)
        metadata["external_subject_id"] = active_session.subject.external_subject_id
        metadata["posture"] = active_session.posture.value
        metadata["time_of_day"] = active_session.time_of_day.value

    await write_audit(
        db,
        action=AuditAction.CALIBRATION_PAIR_RECORDED,
        actor_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        resource=f"calibration:{row.id}",
        metadata=metadata,
    )

    log.info(
        "calibration_pair_recorded",
        calibration_id=str(row.id),
        rppg_hr_bpm=assessment.heart_rate_bpm,
        reference_hr_bpm=payload.reference_hr_bpm,
        error_bpm=round(assessment.heart_rate_bpm - payload.reference_hr_bpm, 3),
        reference_device=payload.reference_device_type.value,
        auto_paired=payload.auto_paired_from_ble,
        reference_rmssd_ms=reference_rmssd,
    )

    return _row_to_response(row)


async def list_calibration_records(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 50,
) -> list[CalibrationRecordResponse]:
    stmt = (
        select(RppgCalibrationRecord)
        .where(RppgCalibrationRecord.user_id == user_id)
        .order_by(desc(RppgCalibrationRecord.created_at))
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    return [_row_to_response(r) for r in rows]


async def calibration_stats(
    db: AsyncSession, *, user_id: uuid.UUID
) -> CalibrationStatsResponse:
    stmt = select(RppgCalibrationRecord).where(
        RppgCalibrationRecord.user_id == user_id
    )
    rows = (await db.scalars(stmt)).all()
    pairs = [
        CalibrationPair(
            rppg_hr_bpm=r.rppg_hr_bpm,
            reference_hr_bpm=r.reference_hr_bpm,
            quality=r.rppg_quality,
            skin_tone=r.skin_tone_estimate.value if r.skin_tone_estimate else None,
            reference_device_type=r.reference_device_type.value,
            rppg_hrv_rmssd_ms=r.rppg_hrv_rmssd_ms,
            reference_hrv_rmssd_ms=r.reference_hrv_rmssd_ms,
            rppg_hrv_sdnn_ms=r.rppg_hrv_sdnn_ms,
            reference_hrv_sdnn_ms=r.reference_hrv_sdnn_ms,
            posture=r.study_session.posture.value if r.study_session else None,
            time_of_day=(
                r.study_session.time_of_day.value if r.study_session else None
            ),
            subject_external_id=(
                r.study_session.subject.external_subject_id
                if r.study_session and r.study_session.subject
                else None
            ),
        )
        for r in rows
    ]
    stratified = compute_stratified(pairs)
    return CalibrationStatsResponse(
        overall=_to_block(stratified.overall),
        overall_hrv=_to_hrv_block(stratified.overall_hrv),
        by_quality={k: _to_block(v) for k, v in stratified.by_quality.items()},
        by_fitzpatrick={k: _to_block(v) for k, v in stratified.by_fitzpatrick.items()},
        by_reference_device={
            k: _to_block(v) for k, v in stratified.by_reference_device.items()
        },
        by_posture={k: _to_block(v) for k, v in stratified.by_posture.items()},
        by_time_of_day={
            k: _to_block(v) for k, v in stratified.by_time_of_day.items()
        },
        by_subject={k: _to_block(v) for k, v in stratified.by_subject.items()},
        pipeline_version=CALIBRATION_VERSION,
    )


async def export_csv(
    db: AsyncSession, *, user_id: uuid.UUID
) -> AsyncIterator[str]:
    stmt = (
        select(RppgCalibrationRecord)
        .where(RppgCalibrationRecord.user_id == user_id)
        .order_by(RppgCalibrationRecord.created_at)
    )
    rows = (await db.scalars(stmt)).all()

    header = StringIO()
    writer = csv.writer(header)
    writer.writerow(
        [
            "timestamp_utc",
            "calibration_id",
            "toi_assessment_id",
            "reference_device_type",
            "reference_device_label",
            "auto_paired_from_ble",
            "reference_hr_bpm",
            "reference_hr_sample_count",
            "reference_rr_bpm",
            "reference_hrv_rmssd_ms",
            "reference_hrv_sdnn_ms",
            "rppg_hr_bpm",
            "rppg_rr_bpm",
            "rppg_hrv_rmssd_ms",
            "rppg_hrv_sdnn_ms",
            "error_bpm",
            "rmssd_error_ms",
            "rppg_quality",
            "rppg_method_selected",
            "rppg_snr_chrom_db",
            "rppg_snr_pos_db",
            "rppg_pipeline_version",
            "skin_tone_estimate",
            "notes",
        ]
    )
    yield header.getvalue()

    for r in rows:
        rmssd_err = (
            f"{r.rppg_hrv_rmssd_ms - r.reference_hrv_rmssd_ms:.3f}"
            if r.rppg_hrv_rmssd_ms is not None
            and r.reference_hrv_rmssd_ms is not None
            else ""
        )
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                r.created_at.isoformat(),
                str(r.id),
                str(r.toi_assessment_id) if r.toi_assessment_id else "",
                r.reference_device_type.value,
                r.reference_device_label or "",
                "true" if r.auto_paired_from_ble else "false",
                f"{r.reference_hr_bpm:.3f}",
                r.reference_hr_sample_count
                if r.reference_hr_sample_count is not None
                else "",
                f"{r.reference_rr_bpm:.3f}" if r.reference_rr_bpm is not None else "",
                f"{r.reference_hrv_rmssd_ms:.3f}"
                if r.reference_hrv_rmssd_ms is not None
                else "",
                f"{r.reference_hrv_sdnn_ms:.3f}"
                if r.reference_hrv_sdnn_ms is not None
                else "",
                f"{r.rppg_hr_bpm:.3f}",
                f"{r.rppg_rr_bpm:.3f}" if r.rppg_rr_bpm is not None else "",
                f"{r.rppg_hrv_rmssd_ms:.3f}" if r.rppg_hrv_rmssd_ms is not None else "",
                f"{r.rppg_hrv_sdnn_ms:.3f}" if r.rppg_hrv_sdnn_ms is not None else "",
                f"{r.rppg_hr_bpm - r.reference_hr_bpm:.3f}",
                rmssd_err,
                r.rppg_quality,
                r.rppg_method_selected,
                f"{r.rppg_snr_chrom_db:.3f}",
                f"{r.rppg_snr_pos_db:.3f}",
                r.rppg_pipeline_version,
                r.skin_tone_estimate.value if r.skin_tone_estimate else "",
                (r.notes or "").replace("\n", " ").replace("\r", " "),
            ]
        )
        yield buf.getvalue()


# --- Helpers -----------------------------------------------------------------


def _to_block(s: CalibrationStats | None) -> CalibrationStatsBlock | None:
    if s is None:
        return None
    return CalibrationStatsBlock(
        n=s.n,
        mae_bpm=s.mae_bpm,
        rmse_bpm=s.rmse_bpm,
        bias_bpm=s.bias_bpm,
        std_diff_bpm=s.std_diff_bpm,
        loa_lower_bpm=s.loa_lower_bpm,
        loa_upper_bpm=s.loa_upper_bpm,
        pearson_r=s.pearson_r,
        pearson_p=s.pearson_p,
        ref_min=s.ref_min,
        ref_max=s.ref_max,
        ref_mean=s.ref_mean,
        means=s.means,
        differences=s.differences,
        flags=s.flags,
    )


def _to_hrv_block(
    s: HrvCalibrationStats | None,
) -> HrvCalibrationStatsBlock | None:
    if s is None:
        return None
    return HrvCalibrationStatsBlock(
        n=s.n,
        rmssd_mae_ms=s.rmssd_mae_ms,
        rmssd_rmse_ms=s.rmssd_rmse_ms,
        rmssd_bias_ms=s.rmssd_bias_ms,
        rmssd_std_diff_ms=s.rmssd_std_diff_ms,
        rmssd_loa_lower_ms=s.rmssd_loa_lower_ms,
        rmssd_loa_upper_ms=s.rmssd_loa_upper_ms,
        rmssd_pearson_r=s.rmssd_pearson_r,
        rmssd_pearson_p=s.rmssd_pearson_p,
        sdnn_mae_ms=s.sdnn_mae_ms,
        sdnn_bias_ms=s.sdnn_bias_ms,
        rmssd_means=s.rmssd_means,
        rmssd_differences=s.rmssd_differences,
        flags=s.flags,
    )


def _row_to_response(row: RppgCalibrationRecord) -> CalibrationRecordResponse:
    quality = ToiQuality(
        row.rppg_quality if isinstance(row.rppg_quality, str) else row.rppg_quality.value
    )
    hrv_error = (
        round(row.rppg_hrv_rmssd_ms - row.reference_hrv_rmssd_ms, 3)
        if row.rppg_hrv_rmssd_ms is not None
        and row.reference_hrv_rmssd_ms is not None
        else None
    )
    return CalibrationRecordResponse(
        id=row.id,
        toi_assessment_id=row.toi_assessment_id,
        reference_device_type=ReferenceDeviceType(row.reference_device_type.value),
        reference_device_label=row.reference_device_label,
        reference_hr_bpm=row.reference_hr_bpm,
        reference_rr_bpm=row.reference_rr_bpm,
        reference_hr_sample_count=row.reference_hr_sample_count,
        reference_hrv_rmssd_ms=row.reference_hrv_rmssd_ms,
        reference_hrv_sdnn_ms=row.reference_hrv_sdnn_ms,
        reference_rr_intervals_ms=row.reference_rr_intervals_ms,
        auto_paired_from_ble=row.auto_paired_from_ble,
        rppg_hr_bpm=row.rppg_hr_bpm,
        rppg_rr_bpm=row.rppg_rr_bpm,
        rppg_hrv_rmssd_ms=row.rppg_hrv_rmssd_ms,
        rppg_hrv_sdnn_ms=row.rppg_hrv_sdnn_ms,
        rppg_quality=quality,
        rppg_method_selected=row.rppg_method_selected,
        rppg_snr_chrom_db=row.rppg_snr_chrom_db,
        rppg_snr_pos_db=row.rppg_snr_pos_db,
        rppg_pipeline_version=row.rppg_pipeline_version,
        skin_tone_estimate=(
            FitzpatrickScale(row.skin_tone_estimate.value)
            if row.skin_tone_estimate
            else None
        ),
        notes=row.notes,
        error_bpm=round(row.rppg_hr_bpm - row.reference_hr_bpm, 3),
        hrv_error_ms=hrv_error,
        study_session_id=row.study_session_id,
        study_subject_external_id=(
            row.study_session.subject.external_subject_id
            if row.study_session and row.study_session.subject
            else None
        ),
        posture=row.study_session.posture.value if row.study_session else None,
        time_of_day=(
            row.study_session.time_of_day.value if row.study_session else None
        ),
        created_at=row.created_at,
    )
