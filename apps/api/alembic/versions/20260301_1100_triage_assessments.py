"""triage_assessments table

Revision ID: 20260301_1100
Revises: 20260301_0900
Create Date: 2026-03-01 11:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1100"
down_revision: str | None = "20260301_0900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RISK_CLASS = postgresql.ENUM(
    "LOW_RISK",
    "ELEVATED_RISK",
    "HIGH_RISK",
    "VERY_HIGH_RISK",
    name="risk_class",
    native_enum=True,
    create_type=False,
)

TRIAGE_STATE = postgresql.ENUM(
    "GREEN",
    "YELLOW",
    "RED",
    name="triage_state",
    native_enum=True,
    create_type=False,
)


def upgrade() -> None:
    RISK_CLASS.create(op.get_bind(), checkfirst=True)
    TRIAGE_STATE.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "triage_assessments",
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
        sa.Column("state", TRIAGE_STATE, nullable=False),
        sa.Column("top_class", RISK_CLASS, nullable=False),
        sa.Column(
            "class_probabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("vacuity", sa.Float(), nullable=False),
        sa.Column("aleatoric_uncertainty", sa.Float(), nullable=False),
        sa.Column("epistemic_uncertainty", sa.Float(), nullable=False),
        sa.Column("dirichlet_strength", sa.Float(), nullable=False),
        sa.Column(
            "raw_inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "derived_features",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "plausibility_flags",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "symptoms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "safety_override_triggered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "override_reasons",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("model_kind", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_triage_assessments_user_id_created_at",
        "triage_assessments",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_triage_assessments_state",
        "triage_assessments",
        ["state"],
    )
    op.create_check_constraint(
        "ck_triage_assessments_vacuity_unit",
        "triage_assessments",
        "vacuity >= 0 AND vacuity <= 1",
    )
    op.create_check_constraint(
        "ck_triage_assessments_uncertainty_nonneg",
        "triage_assessments",
        "aleatoric_uncertainty >= 0 AND epistemic_uncertainty >= 0",
    )


def downgrade() -> None:
    op.drop_index("ix_triage_assessments_state", table_name="triage_assessments")
    op.drop_index(
        "ix_triage_assessments_user_id_created_at",
        table_name="triage_assessments",
    )
    op.drop_table("triage_assessments")
    TRIAGE_STATE.drop(op.get_bind(), checkfirst=True)
    RISK_CLASS.drop(op.get_bind(), checkfirst=True)
