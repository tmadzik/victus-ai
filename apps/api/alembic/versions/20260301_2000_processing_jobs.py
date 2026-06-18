"""processing_jobs queue for the WhatsApp/kiosk capture rail

Revision ID: 20260301_2000
Revises: 20260301_1900
Create Date: 2026-03-01 20:00:00.000000

A database-backed job queue so the WhatsApp webhook can return 200 instantly and
a background worker (cPanel cron or persistent Python app) processes the video
asynchronously with ``FOR UPDATE SKIP LOCKED``. No Redis/Celery on shared hosting.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_2000"
down_revision: str | None = "20260301_1900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JOB_STATUS = postgresql.ENUM(
    "QUEUED",
    "PROCESSING",
    "SUCCEEDED",
    "REJECTED",
    "FAILED",
    name="job_status",
    native_enum=True,
    create_type=False,
)


def upgrade() -> None:
    JOB_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "processing_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "status", JOB_STATUS, nullable=False, server_default="QUEUED"
        ),
        sa.Column(
            "channel", sa.String(16), nullable=False, server_default="WHATSAPP"
        ),
        sa.Column("wa_phone", sa.String(32), nullable=True),
        sa.Column("wa_message_id", sa.String(128), nullable=True),
        sa.Column("media_id", sa.String(255), nullable=True),
        sa.Column("media_path", sa.String(1024), nullable=True),
        sa.Column(
            "language", sa.String(8), nullable=False, server_default="en"
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "intake",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "max_attempts", sa.Integer(), nullable=False, server_default="3"
        ),
        sa.Column(
            "next_attempt_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(4000), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts + 1",
            name="ck_processing_jobs_attempts_bounded",
        ),
    )
    op.create_index(
        "ix_processing_jobs_status_next_attempt",
        "processing_jobs",
        ["status", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "ix_processing_jobs_wa_message_id",
        "processing_jobs",
        ["wa_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_wa_message_id", table_name="processing_jobs")
    op.drop_index(
        "ix_processing_jobs_status_next_attempt", table_name="processing_jobs"
    )
    op.drop_table("processing_jobs")
    JOB_STATUS.drop(op.get_bind(), checkfirst=True)
