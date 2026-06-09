"""toi_assessments table + new audit actions

Revision ID: 20260301_1200
Revises: 20260301_1100
Create Date: 2026-03-01 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1200"
down_revision: str | None = "20260301_1100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TOI_QUALITY = postgresql.ENUM(
    "GOOD",
    "DEGRADED",
    "POOR",
    name="toi_quality",
    native_enum=True,
    create_type=False,
)

FITZPATRICK = postgresql.ENUM(
    "I", "II", "III", "IV", "V", "VI",
    name="fitzpatrick_scale",
    native_enum=True,
    create_type=False,
)


NEW_AUDIT_ACTIONS: tuple[str, ...] = (
    "PATHWAY_B_ASSESSMENT_COMPLETED",
    "PATHWAY_B_QUALITY_REJECTED",
)


def upgrade() -> None:
    TOI_QUALITY.create(op.get_bind(), checkfirst=True)
    FITZPATRICK.create(op.get_bind(), checkfirst=True)

    # Add the two new audit_action enum values to the existing native enum.
    for value in NEW_AUDIT_ACTIONS:
        op.execute(
            sa.text(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
        )

    op.create_table(
        "toi_assessments",
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
        sa.Column("quality", TOI_QUALITY, nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("sample_rate_hz", sa.Float(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False),
        sa.Column("frames_used", sa.Integer(), nullable=False),
        sa.Column("skin_tone_estimate", FITZPATRICK, nullable=True),
        sa.Column("method_selected", sa.String(length=16), nullable=False),
        sa.Column("snr_chrom_db", sa.Float(), nullable=False),
        sa.Column("snr_pos_db", sa.Float(), nullable=False),
        sa.Column("motion_score", sa.Float(), nullable=False),
        sa.Column("lighting_score", sa.Float(), nullable=False),
        sa.Column("face_presence_ratio", sa.Float(), nullable=False),
        sa.Column("heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("heart_rate_ci_low", sa.Float(), nullable=True),
        sa.Column("heart_rate_ci_high", sa.Float(), nullable=True),
        sa.Column("respiratory_rate_bpm", sa.Float(), nullable=True),
        sa.Column("respiratory_rate_ci_low", sa.Float(), nullable=True),
        sa.Column("respiratory_rate_ci_high", sa.Float(), nullable=True),
        sa.Column("hrv_rmssd_ms", sa.Float(), nullable=True),
        sa.Column("hrv_sdnn_ms", sa.Float(), nullable=True),
        sa.Column("stress_index", sa.Float(), nullable=True),
        sa.Column(
            "biomarkers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "signal_quality",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "warnings",
            postgresql.ARRAY(sa.String(length=128)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_toi_assessments_user_id_created_at",
        "toi_assessments",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_toi_assessments_quality", "toi_assessments", ["quality"])
    op.create_check_constraint(
        "ck_toi_assessments_quality_scores_unit",
        "toi_assessments",
        "motion_score >= 0 AND motion_score <= 1 "
        "AND lighting_score >= 0 AND lighting_score <= 1 "
        "AND face_presence_ratio >= 0 AND face_presence_ratio <= 1",
    )


def downgrade() -> None:
    op.drop_index("ix_toi_assessments_quality", table_name="toi_assessments")
    op.drop_index(
        "ix_toi_assessments_user_id_created_at",
        table_name="toi_assessments",
    )
    op.drop_table("toi_assessments")
    FITZPATRICK.drop(op.get_bind(), checkfirst=True)
    TOI_QUALITY.drop(op.get_bind(), checkfirst=True)
    # Postgres does not support removing enum values cleanly; the audit_action
    # values added by upgrade() persist on downgrade.
