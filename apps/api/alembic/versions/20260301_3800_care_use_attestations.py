"""Care-use attestations for the funder / insurer pathway.

Individual member risk is visible only to a care manager who has declared, on
the record, that they are using it for care management and not for underwriting.
This table holds those declarations.

Revision ID: 20260301_3800
Revises: 20260301_3700
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_3800"
down_revision: str | None = "20260301_3700"
branch_labels: str | None = None
depends_on: str | None = None

_NEW_AUDIT_ACTIONS = (
    "CARE_USE_ATTESTED",
    "ORG_COHORT_VIEWED",
    "ORG_MEMBER_RISK_VIEWED",
)


def upgrade() -> None:
    op.create_table(
        "care_use_attestations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column(
            "attested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(400), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Full convention names passed explicitly: `fk` does not embed
    # %(constraint_name)s, so a bare name would land literally and the
    # downgrade would fail to find it.
    op.create_foreign_key(
        "fk_care_use_attestations_user_id_users",
        "care_use_attestations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_care_use_attestations_user_id", "care_use_attestations", ["user_id"]
    )

    for value in _NEW_AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_index(
        "ix_care_use_attestations_user_id", table_name="care_use_attestations"
    )
    op.drop_constraint(
        "fk_care_use_attestations_user_id_users",
        "care_use_attestations",
        type_="foreignkey",
    )
    op.drop_table("care_use_attestations")
    # PostgreSQL cannot drop a value from an enum in place; rebuilding
    # audit_action would rewrite every audit row, which is the one table that
    # must never be rewritten. The three values are left on the type, where
    # nothing can emit them once this table is gone.
