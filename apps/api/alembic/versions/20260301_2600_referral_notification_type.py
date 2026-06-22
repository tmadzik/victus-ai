"""Add the REFERRAL_RAISED notification_type value.

Lets a referral notify the referred participant via the existing notifications
fan-out. Enum-value addition only — no table changes.

Revision ID: 20260301_2600
Revises: 20260301_2500
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_2600"
down_revision: str | None = "20260301_2500"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

NEW_NOTIFICATION_TYPES: tuple[str, ...] = ("REFERRAL_RAISED",)


def upgrade() -> None:
    for value in NEW_NOTIFICATION_TYPES:
        op.execute(
            sa.text(
                f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'"
            )
        )


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value; the label is left in place.
    pass
