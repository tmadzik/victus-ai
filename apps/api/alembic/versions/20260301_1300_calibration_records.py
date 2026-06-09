"""rppg_calibration_records table + ReferenceDeviceType enum + audit action

Revision ID: 20260301_1300
Revises: 20260301_1200
Create Date: 2026-03-01 13:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1300"
down_revision: str | None = "20260301_1200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REFERENCE_DEVICE_TYPE = postgresql.ENUM(
    "PULSE_OXIMETER",
    "SMART_WATCH",
    "ECG_STRAP",
    "MEDICAL_ECG",
    "MANUAL_PULSE_COUNT",
    name="reference_device_type",
    native_enum=True,
    create_type=False,
)


def upgrade() -> None:
    REFERENCE_DEVICE_TYPE.create(op.get_bind(), checkfirst=True)
    op.execute(
        sa.text(
            "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'CALIBRATION_PAIR_RECORDED'"
        )
    )

    op.create_table(
        "rppg_calibration_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "toi_assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("toi_assessments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reference_device_type",
            REFERENCE_DEVICE_TYPE,
            nullable=False,
        ),
        sa.Column("reference_device_label", sa.String(length=120), nullable=True),
        sa.Column("reference_hr_bpm", sa.Float(), nullable=False),
        sa.Column("reference_rr_bpm", sa.Float(), nullable=True),
        # Denormalised rppg metrics — copied at pairing time so the stats
        # endpoint can scan one table without joining to toi_assessments
        # (and so the pair is preserved even if the assessment is later
        # GDPR-erased).
        sa.Column("rppg_hr_bpm", sa.Float(), nullable=False),
        sa.Column("rppg_rr_bpm", sa.Float(), nullable=True),
        sa.Column("rppg_quality", sa.String(length=16), nullable=False),
        sa.Column("rppg_method_selected", sa.String(length=16), nullable=False),
        sa.Column("rppg_snr_chrom_db", sa.Float(), nullable=False),
        sa.Column("rppg_snr_pos_db", sa.Float(), nullable=False),
        sa.Column("rppg_pipeline_version", sa.String(length=32), nullable=False),
        sa.Column(
            "skin_tone_estimate",
            postgresql.ENUM(
                "I", "II", "III", "IV", "V", "VI",
                name="fitzpatrick_scale",
                native_enum=True,
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_rppg_calibration_user_id_created_at",
        "rppg_calibration_records",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_rppg_calibration_toi_assessment_id",
        "rppg_calibration_records",
        ["toi_assessment_id"],
    )
    op.create_check_constraint(
        "ck_rppg_calibration_hr_plausible",
        "rppg_calibration_records",
        "reference_hr_bpm >= 30 AND reference_hr_bpm <= 240 "
        "AND rppg_hr_bpm >= 30 AND rppg_hr_bpm <= 240",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rppg_calibration_toi_assessment_id",
        table_name="rppg_calibration_records",
    )
    op.drop_index(
        "ix_rppg_calibration_user_id_created_at",
        table_name="rppg_calibration_records",
    )
    op.drop_table("rppg_calibration_records")
    REFERENCE_DEVICE_TYPE.drop(op.get_bind(), checkfirst=True)
