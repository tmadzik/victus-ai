"""erasure_requests + nullable PII on users + anonymisation on subjects

Revision ID: 20260301_1600
Revises: 20260301_1500
Create Date: 2026-03-01 16:00:00.000000

GDPR Article 17 / POPIA section 24 erasure flow. We pseudonymise rather than
hard-delete so de-identified research data (assessments, calibration pairs,
sessions) survives — per GDPR Recital 26 anonymised data falls outside the
personal-data regime, and POPIA section 14(3) carves out research retention.
The audit trail itself is preserved as the regulator's evidence that erasure
occurred.

Schema changes:

* ``users.email``, ``users.full_name``, ``users.hashed_password`` become
  nullable. The previous lower(email) unique index is replaced with a
  partial index ``WHERE email IS NOT NULL`` so a second user can re-register
  the same address after the first user's erasure.
* ``users.erased_at`` + ``users.erasure_request_id`` mark the tombstone.
* ``study_subjects.anonymised_at`` + ``study_subjects.erasure_request_id``
  mark per-subject withdrawal.
* New ``erasure_requests`` table: append-only governance ledger with
  jurisdiction, request_basis, target_type, statutory_retention flag.
* New audit_action values for the erasure lifecycle.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_1600"
down_revision: str | None = "20260301_1500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ERASURE_JURISDICTION = postgresql.ENUM(
    "GDPR",
    "POPIA",
    "OTHER",
    name="erasure_jurisdiction",
    native_enum=True,
    create_type=False,
)

ERASURE_BASIS = postgresql.ENUM(
    "DATA_SUBJECT_REQUEST",
    "WITHDRAWN_CONSENT",
    "ACCOUNT_DELETION",
    "ADMIN_ACTION",
    name="erasure_basis",
    native_enum=True,
    create_type=False,
)

ERASURE_TARGET_TYPE = postgresql.ENUM(
    "USER_ACCOUNT",
    "STUDY_SUBJECT",
    "CALIBRATION_RECORD",
    name="erasure_target_type",
    native_enum=True,
    create_type=False,
)

ERASURE_STATUS = postgresql.ENUM(
    "PENDING",
    "COMPLETED",
    "FAILED",
    name="erasure_status",
    native_enum=True,
    create_type=False,
)


NEW_AUDIT_ACTIONS: tuple[str, ...] = (
    "ACCOUNT_ERASURE_REQUESTED",
    "ACCOUNT_ERASED",
    "SUBJECT_ANONYMISATION_REQUESTED",
    "SUBJECT_ANONYMISED",
    "DATA_ACCESS_REQUEST_FULFILLED",
)


def upgrade() -> None:
    ERASURE_JURISDICTION.create(op.get_bind(), checkfirst=True)
    ERASURE_BASIS.create(op.get_bind(), checkfirst=True)
    ERASURE_TARGET_TYPE.create(op.get_bind(), checkfirst=True)
    ERASURE_STATUS.create(op.get_bind(), checkfirst=True)

    for value in NEW_AUDIT_ACTIONS:
        op.execute(
            sa.text(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
        )

    op.create_table(
        "erasure_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # The actor who pressed the button. Can differ from the data subject
        # when an admin / researcher initiates erasure on behalf of someone.
        sa.Column(
            "requesting_actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # The user account being erased, if applicable.
        sa.Column(
            "target_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_type", ERASURE_TARGET_TYPE, nullable=False),
        # Polymorphic — references USER_ACCOUNT.user_id, STUDY_SUBJECT.id, etc.
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("jurisdiction", ERASURE_JURISDICTION, nullable=False),
        sa.Column("request_basis", ERASURE_BASIS, nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            ERASURE_STATUS,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "statutory_retention_applied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "retention_basis",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column("notes", sa.String(length=2000), nullable=True),
    )
    op.create_index(
        "ix_erasure_requests_target",
        "erasure_requests",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_erasure_requests_target_user_id",
        "erasure_requests",
        ["target_user_id"],
    )

    # Relax users PII fields.
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.alter_column(
        "users", "full_name", existing_type=sa.String(length=200), nullable=True
    )
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.add_column(
        "users",
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "erasure_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erasure_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Replace the lower(email) unique index with a partial that ignores NULL
    # — Postgres treats multiple NULLs as distinct, but the *expression*
    # ``lower(NULL)`` is NULL too; the WHERE clause makes the contract
    # explicit and lets a re-registration use a previously-erased address.
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_email_lower"))
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ix_users_email_lower "
            "ON users (lower(email)) WHERE email IS NOT NULL"
        )
    )

    op.add_column(
        "study_subjects",
        sa.Column("anonymised_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "study_subjects",
        sa.Column(
            "erasure_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erasure_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("study_subjects", "erasure_request_id")
    op.drop_column("study_subjects", "anonymised_at")

    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_email_lower"))
    op.execute(
        sa.text("CREATE UNIQUE INDEX ix_users_email_lower ON users (lower(email))")
    )
    op.drop_column("users", "erasure_request_id")
    op.drop_column("users", "erased_at")
    # Note: re-adding NOT NULL would fail if any erased rows exist. Operators
    # should clean up tombstoned users before reversing this migration.
    op.alter_column(
        "users", "hashed_password", existing_type=sa.String(length=255), nullable=False
    )
    op.alter_column(
        "users", "full_name", existing_type=sa.String(length=200), nullable=False
    )
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)

    op.drop_index("ix_erasure_requests_target_user_id", table_name="erasure_requests")
    op.drop_index("ix_erasure_requests_target", table_name="erasure_requests")
    op.drop_table("erasure_requests")

    ERASURE_STATUS.drop(op.get_bind(), checkfirst=True)
    ERASURE_TARGET_TYPE.drop(op.get_bind(), checkfirst=True)
    ERASURE_BASIS.drop(op.get_bind(), checkfirst=True)
    ERASURE_JURISDICTION.drop(op.get_bind(), checkfirst=True)
