"""Referrals — care-navigation referral records + status lifecycle.

Adds the ``referrals`` table (with its three native enums) and two
``audit_action`` values so referral creation and status changes are logged.

Revision ID: 20260301_2500
Revises: 20260301_2400
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_2500"
down_revision: str | None = "20260301_2400"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

URGENCY = postgresql.ENUM(
    "ROUTINE", "URGENT", "EMERGENCY", name="referral_urgency", create_type=False
)
STATUS = postgresql.ENUM(
    "PENDING",
    "ACKNOWLEDGED",
    "COMPLETED",
    "CANCELLED",
    name="referral_status",
    create_type=False,
)
DEST_TYPE = postgresql.ENUM(
    "VICTUS_FACILITY",
    "PUBLIC_CLINIC",
    "HOSPITAL",
    "OTHER",
    name="referral_destination_type",
    create_type=False,
)

NEW_AUDIT_ACTIONS: tuple[str, ...] = ("REFERRAL_CREATED", "REFERRAL_STATUS_UPDATED")


def upgrade() -> None:
    bind = op.get_bind()
    URGENCY.create(bind, checkfirst=True)
    STATUS.create(bind, checkfirst=True)
    DEST_TYPE.create(bind, checkfirst=True)

    for value in NEW_AUDIT_ACTIONS:
        op.execute(
            sa.text(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
        )

    op.create_table(
        "referrals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "participant_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_triage_assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("triage_assessments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("destination_type", DEST_TYPE, nullable=False),
        sa.Column("destination_name", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("urgency", URGENCY, nullable=False),
        sa.Column(
            "status", STATUS, nullable=False, server_default="PENDING"
        ),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_referrals_participant_created",
        "referrals",
        ["participant_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_referrals_participant_created", table_name="referrals")
    op.drop_table("referrals")
    DEST_TYPE.drop(op.get_bind(), checkfirst=True)
    STATUS.drop(op.get_bind(), checkfirst=True)
    URGENCY.drop(op.get_bind(), checkfirst=True)
    # audit_action enum values are left in place (PostgreSQL cannot drop them).
