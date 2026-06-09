"""maker-checker approval gate for erasure requests

Revision ID: 20260301_1700
Revises: 20260301_1600
Create Date: 2026-03-01 17:00:00.000000

Admin-initiated erasures now require a second admin to approve before the
PII is actually destroyed (segregation of duties / maker-checker). The
``erasure_requests`` ledger gains the approval/rejection columns and two
new status values; self-service erasures remain one-shot (a data subject
does not need a second party to erase their own account).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1700"
down_revision: str | None = "20260301_1600"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_STATUS_VALUES: tuple[str, ...] = ("AWAITING_APPROVAL", "REJECTED")
NEW_AUDIT_ACTIONS: tuple[str, ...] = (
    "ERASURE_REQUEST_APPROVED",
    "ERASURE_REQUEST_REJECTED",
)


def upgrade() -> None:
    for value in NEW_STATUS_VALUES:
        op.execute(
            sa.text(f"ALTER TYPE erasure_status ADD VALUE IF NOT EXISTS '{value}'")
        )
    for value in NEW_AUDIT_ACTIONS:
        op.execute(
            sa.text(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
        )

    op.add_column(
        "erasure_requests",
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "erasure_requests",
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "erasure_requests",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "erasure_requests",
        sa.Column(
            "rejected_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "erasure_requests",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "erasure_requests",
        sa.Column("rejection_reason", sa.String(length=2000), nullable=True),
    )
    op.create_index(
        "ix_erasure_requests_status",
        "erasure_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_erasure_requests_status", table_name="erasure_requests")
    op.drop_column("erasure_requests", "rejection_reason")
    op.drop_column("erasure_requests", "rejected_at")
    op.drop_column("erasure_requests", "rejected_by_user_id")
    op.drop_column("erasure_requests", "approved_at")
    op.drop_column("erasure_requests", "approved_by_user_id")
    op.drop_column("erasure_requests", "requires_approval")
    # Postgres enum values added in upgrade() are intentionally left in place;
    # removing enum values requires a full type rebuild and is unsafe if any
    # rows reference them.
