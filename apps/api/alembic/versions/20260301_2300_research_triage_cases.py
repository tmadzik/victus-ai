"""research_triage_cases — labelled triage capture for Model 1 training

Revision ID: 20260301_2300
Revises: 20260301_2200
Create Date: 2026-03-01 23:00:00.000000

A clinician/CHW-entered, ground-truth-labelled triage corpus: real measurements
+ symptoms + confirmed per-disease labels (obesity / hypertension objective from
BMI / BP; diabetes anchored on HbA1c / fasting glucose). Exported to retrain the
multi-head DANN-EDL on recruited data. Reuses the existing ``risk_class`` enum.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_2300"
down_revision: str | None = "20260301_2200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Already created by the triage_assessments migration — reference, don't recreate.
RISK_CLASS = postgresql.ENUM(
    "LOW_RISK",
    "ELEVATED_RISK",
    "HIGH_RISK",
    "VERY_HIGH_RISK",
    name="risk_class",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "research_triage_cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "study_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("study_subjects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "capture_domain",
            sa.String(32),
            nullable=False,
            server_default="CLINICAL_GRADE",
        ),
        sa.Column("age_years", sa.Integer(), nullable=False),
        sa.Column("sex", sa.String(16), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("waist_cm", sa.Float(), nullable=False),
        sa.Column("hip_cm", sa.Float(), nullable=True),
        sa.Column("systolic_bp_mmhg", sa.Float(), nullable=True),
        sa.Column("diastolic_bp_mmhg", sa.Float(), nullable=True),
        sa.Column(
            "safety_triggers",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "contextual",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("fasting_glucose_mmol_l", sa.Float(), nullable=True),
        sa.Column("hba1c_percent", sa.Float(), nullable=True),
        sa.Column("obesity_label", RISK_CLASS, nullable=False),
        sa.Column("hypertension_label", RISK_CLASS, nullable=False),
        sa.Column("diabetes_label", RISK_CLASS, nullable=False),
        sa.Column(
            "label_basis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_research_triage_cases_study_subject_id",
        "research_triage_cases",
        ["study_subject_id"],
    )
    op.create_index(
        "ix_research_triage_cases_created_at", "research_triage_cases", ["created_at"]
    )
    op.create_index(
        "ix_research_triage_cases_capture_domain",
        "research_triage_cases",
        ["capture_domain"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_triage_cases_capture_domain", table_name="research_triage_cases"
    )
    op.drop_index(
        "ix_research_triage_cases_created_at", table_name="research_triage_cases"
    )
    op.drop_index(
        "ix_research_triage_cases_study_subject_id", table_name="research_triage_cases"
    )
    op.drop_table("research_triage_cases")
