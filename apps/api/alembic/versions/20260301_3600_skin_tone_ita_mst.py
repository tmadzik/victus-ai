"""Skin tone: Monk Skin Tone + measured ITA°, per validation plan §3/§5.

Fitzpatrick is retired as the *analysis* variable (it grades UV photosensitivity,
not pigmentation, and gives two categories for everything darker than IV — the
range this platform operates in). It is deliberately **retained** as a recorded
secondary for comparability with the existing rPPG literature, so no column is
dropped here; this migration is purely additive.

Placement follows how each value behaves:

* ``study_subjects.monk_skin_tone`` — a stable descriptor of the person, on a
  table that by design carries no PII.
* ``rppg_calibration_records.ita_forehead_degrees`` — measured *per capture*,
  because facultative (sun-exposed) pigment at the forehead ROI varies over
  time, and the forehead is the skin the camera actually reads.

Revision ID: 20260301_3600
Revises: 20260301_3500
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_3600"
down_revision: str | None = "20260301_3500"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "study_subjects",
        sa.Column("monk_skin_tone", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        "monk_skin_tone_range",
        "study_subjects",
        "monk_skin_tone IS NULL OR (monk_skin_tone BETWEEN 1 AND 10)",
    )

    op.add_column(
        "rppg_calibration_records",
        sa.Column("ita_forehead_degrees", sa.Float(), nullable=True),
    )
    # ITA° = arctan((L* − 50) / b*) × 180/π. Mathematically bounded to ±90°;
    # real skin spans roughly −70°…+70°. The guard catches unit errors (radians
    # posted as degrees) rather than policing physiology.
    op.create_check_constraint(
        "ita_forehead_degrees_range",
        "rppg_calibration_records",
        "ita_forehead_degrees IS NULL OR (ita_forehead_degrees BETWEEN -90 AND 90)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ita_forehead_degrees_range", "rppg_calibration_records", type_="check"
    )
    op.drop_column("rppg_calibration_records", "ita_forehead_degrees")
    op.drop_constraint(
        "monk_skin_tone_range", "study_subjects", type_="check"
    )
    op.drop_column("study_subjects", "monk_skin_tone")
