"""Organisations: the funder / insurer tenancy boundary.

Tenancy is a *deployment* boundary — one instance, one database, one
organisation — so this migration adds the organisation's identity rather than
any cross-tenant scoping machinery. There is deliberately no
``WHERE organisation_id = ...`` path to get wrong.

Additive and reversible: existing Victus research and pilot deployments serve no
organisation, so ``users.organisation_id`` is NULL there and nothing changes.

Revision ID: 20260301_3700
Revises: 20260301_3500
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_3700"
down_revision: str | None = "20260301_3500"
branch_labels: str | None = None
depends_on: str | None = None

# Created explicitly in upgrade(); `create_type=False` stops create_table()
# from emitting a second CREATE TYPE for the same enum.
SERVICE_MODEL = postgresql.ENUM(
    "PLATFORM",
    "FACILITIES",
    "IN_HOUSE",
    name="service_model",
    create_type=False,
)


def upgrade() -> None:
    SERVICE_MODEL.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "organisations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_code", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("service_model", SERVICE_MODEL, nullable=False),
        sa.Column(
            "training_export_consent",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("training_export_consent_version", sa.String(64), nullable=True),
        sa.Column(
            "training_export_consent_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Full convention names are passed explicitly: the `ck` convention embeds
    # %(constraint_name)s so a bare name gets expanded, but `uq` and `fk` do
    # not, so a bare name there would land literally and the downgrade would
    # then fail to find it.
    op.create_unique_constraint(
        "uq_organisations_org_code", "organisations", ["org_code"]
    )
    # Consent must name the agreement that was signed. A bare TRUE cannot be
    # audited later, and "which terms did they agree to" is exactly the question
    # asked when the terms change.
    op.create_check_constraint(
        "export_consent_needs_version",
        "organisations",
        "training_export_consent IS FALSE "
        "OR training_export_consent_version IS NOT NULL",
    )

    op.add_column(
        "users",
        sa.Column(
            "organisation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_users_organisation_id_organisations",
        "users",
        "organisations",
        ["organisation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_users_organisation_id", "users", ["organisation_id"]
    )

    # Organisation-side roles. Added to the existing native enum rather than a
    # parallel column so a single role check keeps covering every user.
    for value in ("ORG_ADMIN", "CARE_MANAGER"):
        op.execute(f"ALTER TYPE user_role ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_index("ix_users_organisation_id", table_name="users")
    op.drop_constraint(
        "fk_users_organisation_id_organisations", "users", type_="foreignkey"
    )
    op.drop_column("users", "organisation_id")
    op.drop_table("organisations")
    SERVICE_MODEL.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot remove a value from an enum type in place. Rebuilding
    # user_role would rewrite every users row and break any FK-less reference in
    # flight, so ORG_ADMIN / CARE_MANAGER are left on the type. They are
    # unreachable once organisations is gone: no user can hold them, because
    # nothing assigns them without an organisation.
