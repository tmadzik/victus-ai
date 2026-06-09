"""study_subjects + study_sessions + FK on calibration records

Revision ID: 20260301_1500
Revises: 20260301_1400
Create Date: 2026-03-01 15:00:00.000000

IRB-style pre-registration: every calibration capture inherits a locked
``study_session`` (posture, ambient lux, time-of-day, caffeine / nicotine /
exercise covariates) attached to an anonymous ``study_subject`` identified
by a researcher-assigned ``external_subject_id``. The session locks on first
capture so cohort parameters cannot drift mid-study.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1500"
down_revision: str | None = "20260301_1400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEX_AT_BIRTH = postgresql.ENUM(
    "MALE",
    "FEMALE",
    "INTERSEX",
    "PREFER_NOT_TO_SAY",
    name="sex_assigned_at_birth",
    native_enum=True,
    create_type=False,
)

POSTURE = postgresql.ENUM(
    "SITTING",
    "STANDING",
    "SUPINE",
    "SEMI_RECLINED",
    name="study_posture",
    native_enum=True,
    create_type=False,
)

TIME_OF_DAY = postgresql.ENUM(
    "MORNING",
    "AFTERNOON",
    "EVENING",
    "NIGHT",
    name="time_of_day",
    native_enum=True,
    create_type=False,
)


NEW_AUDIT_ACTIONS: tuple[str, ...] = (
    "STUDY_SUBJECT_CREATED",
    "STUDY_SESSION_STARTED",
    "STUDY_SESSION_LOCKED",
    "STUDY_SESSION_ENDED",
)


def upgrade() -> None:
    SEX_AT_BIRTH.create(op.get_bind(), checkfirst=True)
    POSTURE.create(op.get_bind(), checkfirst=True)
    TIME_OF_DAY.create(op.get_bind(), checkfirst=True)

    for value in NEW_AUDIT_ACTIONS:
        op.execute(
            sa.text(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
        )

    op.create_table(
        "study_subjects",
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
        sa.Column("external_subject_id", sa.String(length=64), nullable=False),
        sa.Column("age_years", sa.Integer(), nullable=False),
        sa.Column("sex_assigned_at_birth", SEX_AT_BIRTH, nullable=False),
        sa.Column(
            "fitzpatrick_scale",
            postgresql.ENUM(
                "I", "II", "III", "IV", "V", "VI",
                name="fitzpatrick_scale",
                native_enum=True,
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("medical_history_summary", sa.String(length=2000), nullable=True),
        sa.Column(
            "consent_protocol_version", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.UniqueConstraint(
            "user_id",
            "external_subject_id",
            name="uq_study_subjects_user_ext_id",
        ),
        sa.CheckConstraint(
            "age_years >= 0 AND age_years <= 130", name="ck_study_subjects_age"
        ),
        sa.CheckConstraint(
            "(height_cm IS NULL OR (height_cm > 0 AND height_cm <= 250)) AND "
            "(weight_kg IS NULL OR (weight_kg > 0 AND weight_kg <= 400))",
            name="ck_study_subjects_anthropometrics",
        ),
    )
    op.create_index(
        "ix_study_subjects_user_id_enrolled_at",
        "study_subjects",
        ["user_id", sa.text("enrolled_at DESC")],
    )

    op.create_table(
        "study_sessions",
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
        sa.Column(
            "study_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("study_subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "session_started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("posture", POSTURE, nullable=False),
        sa.Column("time_of_day", TIME_OF_DAY, nullable=False),
        sa.Column("ambient_lux", sa.Float(), nullable=True),
        sa.Column("ambient_temperature_c", sa.Float(), nullable=True),
        sa.Column("room_humidity_pct", sa.Float(), nullable=True),
        sa.Column("fasted_hours", sa.Float(), nullable=True),
        sa.Column(
            "caffeine_within_2h",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "nicotine_within_2h",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "alcohol_within_24h",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "last_exercise_hours_ago", sa.Float(), nullable=True
        ),
        sa.Column(
            "recording_site_label", sa.String(length=120), nullable=True
        ),
        sa.Column("protocol_version", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column(
            "is_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(ambient_lux IS NULL OR ambient_lux >= 0) AND "
            "(ambient_temperature_c IS NULL OR ambient_temperature_c BETWEEN -20 AND 60) AND "
            "(room_humidity_pct IS NULL OR room_humidity_pct BETWEEN 0 AND 100) AND "
            "(fasted_hours IS NULL OR fasted_hours BETWEEN 0 AND 72) AND "
            "(last_exercise_hours_ago IS NULL OR last_exercise_hours_ago BETWEEN 0 AND 168)",
            name="ck_study_sessions_covariate_ranges",
        ),
    )
    op.create_index(
        "ix_study_sessions_user_id_started_at",
        "study_sessions",
        ["user_id", sa.text("session_started_at DESC")],
    )
    op.create_index(
        "ix_study_sessions_subject_id_started_at",
        "study_sessions",
        ["study_subject_id", sa.text("session_started_at DESC")],
    )
    # At most one ACTIVE (not-ended) session per user — keeps the
    # auto-attach calibration logic unambiguous.
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_study_sessions_active_per_user "
            "ON study_sessions(user_id) WHERE ended_at IS NULL"
        )
    )

    op.add_column(
        "rppg_calibration_records",
        sa.Column(
            "study_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("study_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_rppg_calibration_study_session_id",
        "rppg_calibration_records",
        ["study_session_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rppg_calibration_study_session_id",
        table_name="rppg_calibration_records",
    )
    op.drop_column("rppg_calibration_records", "study_session_id")

    op.execute(sa.text("DROP INDEX IF EXISTS uq_study_sessions_active_per_user"))
    op.drop_index(
        "ix_study_sessions_subject_id_started_at", table_name="study_sessions"
    )
    op.drop_index(
        "ix_study_sessions_user_id_started_at", table_name="study_sessions"
    )
    op.drop_table("study_sessions")
    op.drop_index(
        "ix_study_subjects_user_id_enrolled_at", table_name="study_subjects"
    )
    op.drop_table("study_subjects")
    TIME_OF_DAY.drop(op.get_bind(), checkfirst=True)
    POSTURE.drop(op.get_bind(), checkfirst=True)
    SEX_AT_BIRTH.drop(op.get_bind(), checkfirst=True)
