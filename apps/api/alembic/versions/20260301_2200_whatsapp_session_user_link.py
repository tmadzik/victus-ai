"""whatsapp_sessions.user_id — phone → pseudonymous User identity bridge

Revision ID: 20260301_2200
Revises: 20260301_2100
Create Date: 2026-03-01 22:00:00.000000

Links a WhatsApp conversation to a pseudonymous ``users`` row created when the
participant grants consent. With this link, captures persist to the clinician
app (the worker fills ``processing_jobs.user_id``) and the participant falls
under the standard account-erasure flow. No PII is added to ``users`` — the
phone stays only on ``whatsapp_sessions`` (deleted on STOP/erasure) and
``processing_jobs`` (scrubbed). ``ON DELETE SET NULL`` so a tombstoned user
never cascade-deletes the separately-scrubbed session.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_2200"
down_revision: str | None = "20260301_2100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_whatsapp_sessions_user_id",
        "whatsapp_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_whatsapp_sessions_user_id", "whatsapp_sessions", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_sessions_user_id", table_name="whatsapp_sessions")
    op.drop_constraint(
        "fk_whatsapp_sessions_user_id", "whatsapp_sessions", type_="foreignkey"
    )
    op.drop_column("whatsapp_sessions", "user_id")
