"""Add the CDPA erasure_jurisdiction value (Zimbabwe pilot).

Zimbabwe's data-protection regime is the Cyber and Data Protection Act
[Chapter 12:07] (2021), supervised by POTRAZ as the Data Protection Authority —
distinct from GDPR / POPIA / NDPA. Zimbabwe was previously mislabelled as POPIA
(a South African statute with no force in Zimbabwe); this adds its own value so
ZW-site erasures record the governing law correctly. Enum-value addition only —
no table changes.

Revision ID: 20260301_3000
Revises: 20260301_2900
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_3000"
down_revision: str | None = "20260301_2900"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None

NEW_JURISDICTIONS: tuple[str, ...] = ("CDPA",)


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
