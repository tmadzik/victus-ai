"""rppg_calibration_records BLE auto-pair extensions

Revision ID: 20260301_1400
Revises: 20260301_1300
Create Date: 2026-03-01 14:00:00.000000

Adds the columns required to persist BLE-streamed reference HR + RR-intervals
captured during the same 30-s window as the rPPG run. The RR intervals enable
gold-standard HRV agreement metrics (vs the rPPG-derived RMSSD/SDNN).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1400"
down_revision: str | None = "20260301_1300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rppg_calibration_records",
        sa.Column(
            "auto_paired_from_ble",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "rppg_calibration_records",
        sa.Column("reference_hr_sample_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "rppg_calibration_records",
        sa.Column("reference_hrv_rmssd_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "rppg_calibration_records",
        sa.Column("reference_hrv_sdnn_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "rppg_calibration_records",
        sa.Column(
            "reference_rr_intervals_ms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "rppg_calibration_records",
        sa.Column("rppg_hrv_rmssd_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "rppg_calibration_records",
        sa.Column("rppg_hrv_sdnn_ms", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_rppg_calibration_auto_paired",
        "rppg_calibration_records",
        ["auto_paired_from_ble"],
    )
    op.create_check_constraint(
        "ck_rppg_calibration_hrv_nonneg",
        "rppg_calibration_records",
        "(reference_hrv_rmssd_ms IS NULL OR reference_hrv_rmssd_ms >= 0) AND "
        "(reference_hrv_sdnn_ms IS NULL OR reference_hrv_sdnn_ms >= 0) AND "
        "(rppg_hrv_rmssd_ms IS NULL OR rppg_hrv_rmssd_ms >= 0) AND "
        "(rppg_hrv_sdnn_ms IS NULL OR rppg_hrv_sdnn_ms >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_rppg_calibration_hrv_nonneg",
        "rppg_calibration_records",
        type_="check",
    )
    op.drop_index(
        "ix_rppg_calibration_auto_paired",
        table_name="rppg_calibration_records",
    )
    for col in (
        "rppg_hrv_sdnn_ms",
        "rppg_hrv_rmssd_ms",
        "reference_rr_intervals_ms",
        "reference_hrv_sdnn_ms",
        "reference_hrv_rmssd_ms",
        "reference_hr_sample_count",
        "auto_paired_from_ble",
    ):
        op.drop_column("rppg_calibration_records", col)
