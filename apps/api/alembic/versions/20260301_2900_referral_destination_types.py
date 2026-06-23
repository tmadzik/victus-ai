"""Add Nigeria-relevant referral_destination_type values.

PRIMARY_HEALTH_CENTRE (public PHC) and TEACHING_HOSPITAL (tertiary) reflect the
Nigerian health-system tiers — Victus does not own facilities there, so referrals
flow into the public system. Enum-value addition only.

Revision ID: 20260301_2900
Revises: 20260301_2800
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_2900"
down_revision: str | None = "20260301_2800"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

NEW_TYPES: tuple[str, ...] = ("PRIMARY_HEALTH_CENTRE", "TEACHING_HOSPITAL")


def upgrade() -> None:
    for value in NEW_TYPES:
        op.execute(
            sa.text(
                "ALTER TYPE referral_destination_type "
                f"ADD VALUE IF NOT EXISTS '{value}'"
            )
        )


def downgrade() -> None:
    # PostgreSQL cannot drop enum values; labels are left in place.
    pass
