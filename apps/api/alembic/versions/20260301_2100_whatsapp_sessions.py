"""whatsapp_sessions — per-phone conversation state for the WhatsApp rail

Revision ID: 20260301_2100
Revises: 20260301_2000
Create Date: 2026-03-01 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_2100"
down_revision: str | None = "20260301_2000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column(
            "state", sa.String(16), nullable=False, server_default="LANGUAGE"
        ),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column(
            "consent", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "intake",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "audit_index", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "safety_triggers",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "contextual",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("last_message_id", sa.String(128), nullable=True),
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
        "ix_whatsapp_sessions_phone",
        "whatsapp_sessions",
        ["phone"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_sessions_phone", table_name="whatsapp_sessions")
    op.drop_table("whatsapp_sessions")
