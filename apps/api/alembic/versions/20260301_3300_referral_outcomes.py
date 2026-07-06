"""Referral outcomes — close the care loop with a facility-confirmed result.

Adds the ``referral_outcome`` native enum, three nullable/defaulted columns on
``referrals`` (outcome, outcome_recorded_at, outcome_notes), and the
``REFERRAL_OUTCOME_RECORDED`` audit action. Additive only.

Revision ID: 20260301_3300
Revises: 20260301_3200
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_3300"
down_revision: str | None = "20260301_3200"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

OUTCOME = postgresql.ENUM(
    "PENDING",
    "ATTENDED_CONFIRMED",
    "ATTENDED_NOT_CONFIRMED",
    "ATTENDED_INCONCLUSIVE",
    "TREATMENT_STARTED",
    "DID_NOT_ATTEND",
    "DECLINED_CARE",
    name="referral_outcome",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    OUTCOME.create(bind, checkfirst=True)

    op.execute(
        sa.text(
            "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS "
            "'REFERRAL_OUTCOME_RECORDED'"
        )
    )

    op.add_column(
        "referrals",
        sa.Column(
            "outcome",
            OUTCOME,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "referrals",
        sa.Column(
            "outcome_recorded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "referrals",
        sa.Column("outcome_notes", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("referrals", "outcome_notes")
    op.drop_column("referrals", "outcome_recorded_at")
    op.drop_column("referrals", "outcome")
    OUTCOME.drop(op.get_bind(), checkfirst=True)
    # The audit_action enum value is left in place (PostgreSQL cannot drop one).
