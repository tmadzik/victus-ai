"""notifications table + NotificationType enum

Revision ID: 20260301_1800
Revises: 20260301_1700
Create Date: 2026-03-01 18:00:00.000000

In-app notifications so the erasure-approval queue is push, not pull. When a
maker proposes an erasure that requires approval, every eligible checker (all
active admins except the maker) receives a row here. A best-effort webhook
(Slack-compatible) is dispatched separately and is not persisted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1800"
down_revision: str | None = "20260301_1700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NOTIFICATION_TYPE = postgresql.ENUM(
    "ERASURE_APPROVAL_REQUESTED",
    "ERASURE_REQUEST_APPROVED",
    "ERASURE_REQUEST_REJECTED",
    "GENERIC",
    name="notification_type",
    native_enum=True,
    create_type=False,
)


def upgrade() -> None:
    NOTIFICATION_TYPE.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "recipient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", NOTIFICATION_TYPE, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        # In-app deep link (e.g. /admin/governance?tab=pending).
        sa.Column("resource", sa.String(length=512), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_notifications_recipient_created_at",
        "notifications",
        ["recipient_user_id", sa.text("created_at DESC")],
    )
    # Partial index over unread rows — the unread-count query hits this hot path.
    op.execute(
        sa.text(
            "CREATE INDEX ix_notifications_recipient_unread "
            "ON notifications(recipient_user_id) WHERE read_at IS NULL"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_notifications_recipient_unread"))
    op.drop_index(
        "ix_notifications_recipient_created_at", table_name="notifications"
    )
    op.drop_table("notifications")
    NOTIFICATION_TYPE.drop(op.get_bind(), checkfirst=True)
