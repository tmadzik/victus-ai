"""Front-of-platform enrollment: participant_profiles.

A single identified-demographics + consent capture that gates access to both
pathways. Direct identifiers (name, email) and self-reported race/ethnicity make
this IDENTIFIED special-category data; the external patient id is stored only as
a salted one-way hash. Reuses the existing ``sex_assigned_at_birth`` enum.

Revision ID: 20260301_3200
Revises: 20260301_3100
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_3200"
down_revision: str | None = "20260301_3100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Existing native enum — do NOT create it here.
SEX_AT_BIRTH = postgresql.ENUM(
    "MALE",
    "FEMALE",
    "INTERSEX",
    "PREFER_NOT_TO_SAY",
    name="sex_assigned_at_birth",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "participant_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Direct identifiers — tombstoned on erasure.
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        # Salted one-way hash of the external patient id (never plaintext).
        sa.Column("patient_id_hash", sa.String(64), nullable=True),
        sa.Column("age_range", sa.String(16), nullable=False),
        sa.Column("biological_sex", SEX_AT_BIRTH, nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("race_ethnicity", sa.String(64), nullable=True),
        sa.Column(
            "jurisdiction", sa.String(16), nullable=False, server_default="OTHER"
        ),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_participant_profiles_user_id",
        "participant_profiles",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_participant_profiles_patient_id_hash",
        "participant_profiles",
        ["patient_id_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_participant_profiles_patient_id_hash",
        table_name="participant_profiles",
    )
    op.drop_index(
        "ix_participant_profiles_user_id", table_name="participant_profiles"
    )
    op.drop_table("participant_profiles")
