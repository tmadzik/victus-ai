"""Add the NDPA erasure_jurisdiction value (Nigeria pilot).

Nigeria's data-protection regime is the NDPA 2023 (regulator: NDPC), distinct
from GDPR / POPIA. Enum-value addition only — no table changes.

Revision ID: 20260301_2700
Revises: 20260301_2600
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_2700"
down_revision: str | None = "20260301_2600"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

NEW_JURISDICTIONS: tuple[str, ...] = ("NDPA",)


def upgrade() -> None:
    for value in NEW_JURISDICTIONS:
        op.execute(
            sa.text(
                f"ALTER TYPE erasure_jurisdiction ADD VALUE IF NOT EXISTS '{value}'"
            )
        )


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value; the label is left in place.
    pass
