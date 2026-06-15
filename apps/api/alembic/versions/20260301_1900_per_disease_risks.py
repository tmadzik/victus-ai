"""per-disease risk decomposition on triage_assessments

Revision ID: 20260301_1900
Revises: 20260301_1800
Create Date: 2026-03-01 19:00:00.000000

Pathway A now weights obesity, hypertension and diabetes independently — each
gets its own Dirichlet over the four risk tiers, its own uncertainty
decomposition and its own GREEN/YELLOW/RED state. The authoritative breakdown
is stored as a JSONB array of ``PerDiseaseRisk`` objects.

The pre-existing single-risk columns (``state``, ``top_class``, ``vacuity`` …)
are retained: they now hold the *overall summary* — the worst-state disease —
so existing indexes, history reads and analytics keep working. This migration
is therefore purely additive. Existing rows are backfilled with a single-entry
breakdown synthesised from their legacy summary so the API can render history
uniformly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1900"
down_revision: str | None = "20260301_1800"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "triage_assessments",
        sa.Column(
            "per_disease_risks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # Backfill legacy rows with an OBESITY-tagged single entry derived from the
    # existing overall summary, so /triage history renders without nulls. New
    # rows always write the full three-disease breakdown.
    op.execute(
        """
        UPDATE triage_assessments
        SET per_disease_risks = jsonb_build_array(
            jsonb_build_object(
                'disease', 'OBESITY',
                'state', state::text,
                'top_class', top_class::text,
                'class_probabilities', class_probabilities,
                'evidence', evidence,
                'uncertainty', jsonb_build_object(
                    'vacuity', vacuity,
                    'aleatoric', aleatoric_uncertainty,
                    'epistemic', epistemic_uncertainty,
                    'strength', dirichlet_strength
                ),
                'contributing_factors', '[]'::jsonb,
                'next_action', '(historical)'
            )
        )
        WHERE per_disease_risks = '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.drop_column("triage_assessments", "per_disease_risks")
