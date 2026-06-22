"""Add the CLINICIAN_PARTICIPANT_VIEWED audit action.

The clinician participant-review surface reuses existing tables (triage_assessments,
toi_assessments, users); the only schema change is one new audit_action enum value
so every clinician access to an identified participant is logged.

Revision ID: 20260301_2400
Revises: 20260301_2300
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_2400"
down_revision: str | None = "20260301_2300"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

NEW_AUDIT_ACTIONS: tuple[str, ...] = ("CLINICIAN_PARTICIPANT_VIEWED",)


def upgrade() -> None:
    for value in NEW_AUDIT_ACTIONS:
        op.execute(
            sa.text(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
        )


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type; the added label is
    # harmless if left in place (mirrors the other audit_action additions).
    pass
