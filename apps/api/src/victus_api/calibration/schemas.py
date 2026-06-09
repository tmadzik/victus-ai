"""Pydantic v2 DTOs for the rPPG calibration domain."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from victus_api.toi.schemas import FitzpatrickScale, ToiQuality


class ReferenceDeviceType(str, enum.Enum):
    PULSE_OXIMETER = "PULSE_OXIMETER"
    SMART_WATCH = "SMART_WATCH"
    ECG_STRAP = "ECG_STRAP"
    MEDICAL_ECG = "MEDICAL_ECG"
    MANUAL_PULSE_COUNT = "MANUAL_PULSE_COUNT"


class RecordCalibrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    toi_assessment_id: uuid.UUID
    reference_device_type: ReferenceDeviceType
    reference_device_label: str | None = Field(default=None, max_length=120)
    reference_hr_bpm: Annotated[float, Field(ge=30.0, le=240.0)]
    reference_rr_bpm: Annotated[float, Field(ge=4.0, le=60.0)] | None = None
    # BLE-auto-paired data — all optional so manual pairing still works.
    auto_paired_from_ble: bool = False
    reference_hr_sample_count: Annotated[int, Field(ge=0)] | None = None
    reference_rr_intervals_ms: list[
        Annotated[float, Field(ge=250.0, le=2000.0)]
    ] | None = None
    skin_tone_estimate: FitzpatrickScale | None = None
    notes: str | None = Field(default=None, max_length=500)


class CalibrationRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    toi_assessment_id: uuid.UUID | None
    reference_device_type: ReferenceDeviceType
    reference_device_label: str | None
    reference_hr_bpm: float
    reference_rr_bpm: float | None
    reference_hr_sample_count: int | None
    reference_hrv_rmssd_ms: float | None
    reference_hrv_sdnn_ms: float | None
    reference_rr_intervals_ms: list[float] | None
    auto_paired_from_ble: bool
    rppg_hr_bpm: float
    rppg_rr_bpm: float | None
    rppg_hrv_rmssd_ms: float | None
    rppg_hrv_sdnn_ms: float | None
    rppg_quality: ToiQuality
    rppg_method_selected: str
    rppg_snr_chrom_db: float
    rppg_snr_pos_db: float
    rppg_pipeline_version: str
    skin_tone_estimate: FitzpatrickScale | None
    notes: str | None
    error_bpm: float  # rppg_hr − reference_hr (signed)
    hrv_error_ms: float | None  # rppg_rmssd − reference_rmssd (signed), if both present
    # Pre-registered study context (null if the pair was recorded outside a
    # study session — manual pairing without an active session).
    study_session_id: uuid.UUID | None
    study_subject_external_id: str | None
    posture: str | None
    time_of_day: str | None
    created_at: datetime


class CalibrationStatsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    mae_bpm: float
    rmse_bpm: float
    bias_bpm: float
    std_diff_bpm: float
    loa_lower_bpm: float
    loa_upper_bpm: float
    pearson_r: float | None
    pearson_p: float | None
    ref_min: float
    ref_max: float
    ref_mean: float
    means: list[float]
    differences: list[float]
    flags: list[str]


class HrvCalibrationStatsBlock(BaseModel):
    """Bland-Altman + agreement statistics on HRV (RMSSD/SDNN).

    A pair is only included if BOTH ``reference_hrv_rmssd_ms`` and
    ``rppg_hrv_rmssd_ms`` are present. Pulse oximeters that expose only HR
    via 0x180D will yield HR-only pairs, which are still useful for the HR
    block but contribute nothing here.
    """

    model_config = ConfigDict(extra="forbid")

    n: int
    rmssd_mae_ms: float
    rmssd_rmse_ms: float
    rmssd_bias_ms: float
    rmssd_std_diff_ms: float
    rmssd_loa_lower_ms: float
    rmssd_loa_upper_ms: float
    rmssd_pearson_r: float | None
    rmssd_pearson_p: float | None
    sdnn_mae_ms: float | None
    sdnn_bias_ms: float | None
    rmssd_means: list[float]
    rmssd_differences: list[float]
    flags: list[str]


class CalibrationStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: CalibrationStatsBlock | None
    overall_hrv: HrvCalibrationStatsBlock | None
    by_quality: dict[str, CalibrationStatsBlock | None]
    by_fitzpatrick: dict[str, CalibrationStatsBlock | None]
    by_reference_device: dict[str, CalibrationStatsBlock | None]
    by_posture: dict[str, CalibrationStatsBlock | None]
    by_time_of_day: dict[str, CalibrationStatsBlock | None]
    by_subject: dict[str, CalibrationStatsBlock | None]
    pipeline_version: str
