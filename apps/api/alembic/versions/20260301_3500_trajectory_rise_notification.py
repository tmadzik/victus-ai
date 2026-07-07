"""Add the RISK_TRAJECTORY_RISE notification_type value.

Fired to a participant's site clinicians when a new assessment tips a disease's
risk into a significant upward trajectory. Enum-value addition only.

Revision ID: 20260301_3500
Revises: 20260301_3400
Create Date: 2026-06-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_3500"
down_revision: str | None = "20260301_3400"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TYPE notification_type ADD VALUE IF NOT EXISTS "
            "'RISK_TRAJECTORY_RISE'"
        )
    )


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value; the label is left in place.
    pass
