"""Add site_code to users and research_triage_cases (multi-country pilot).

Each pilot deployment (e.g. Zimbabwe, Nigeria) stamps its participants and
research cases with a site code for residency partitioning, per-site analytics,
and geography-stratified model calibration.

Revision ID: 20260301_2800
Revises: 20260301_2700
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_2800"
down_revision: str | None = "20260301_2700"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table in ("users", "research_triage_cases"):
        op.add_column(
            table,
            sa.Column(
                "site_code",
                sa.String(length=16),
                nullable=False,
                server_default="DEFAULT",
            ),
        )
        op.create_index(f"ix_{table}_site_code", table, ["site_code"])


def downgrade() -> None:
    for table in ("research_triage_cases", "users"):
        op.drop_index(f"ix_{table}_site_code", table_name=table)
        op.drop_column(table, "site_code")
