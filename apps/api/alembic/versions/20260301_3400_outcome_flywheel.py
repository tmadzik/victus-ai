"""Care-loop flywheel — confirmed glycaemia on referrals + research-case link.

Adds the facility-confirmed diabetes markers to ``referrals``
(outcome_hba1c_percent, outcome_fasting_glucose_mmol_l) and a provenance link on
``research_triage_cases`` (source_triage_assessment_id) so a confirmed outcome
can seed a labelled training row from the originating assessment. Additive only.

Revision ID: 20260301_3400
Revises: 20260301_3300
Create Date: 2026-06-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_3400"
down_revision: str | None = "20260301_3300"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "referrals",
        sa.Column("outcome_hba1c_percent", sa.Float(), nullable=True),
    )
    op.add_column(
        "referrals",
        sa.Column("outcome_fasting_glucose_mmol_l", sa.Float(), nullable=True),
    )
    op.add_column(
        "research_triage_cases",
        sa.Column(
            "source_triage_assessment_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_research_case_source_assessment",
        "research_triage_cases",
        "triage_assessments",
        ["source_triage_assessment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_research_cases_source_assessment",
        "research_triage_cases",
        ["source_triage_assessment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_cases_source_assessment", table_name="research_triage_cases"
    )
    op.drop_constraint(
        "fk_research_case_source_assessment",
        "research_triage_cases",
        type_="foreignkey",
    )
    op.drop_column("research_triage_cases", "source_triage_assessment_id")
    op.drop_column("referrals", "outcome_fasting_glucose_mmol_l")
    op.drop_column("referrals", "outcome_hba1c_percent")
