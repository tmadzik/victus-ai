"""Mobile Clinic Gateway — kiosk capture rail schema.

Adds the four tables that back the public-kiosk capture surface. The kiosk
reuses the existing identity (``users``), conversation (``whatsapp_sessions``)
and async-processing (``processing_jobs``) rails rather than forking them — so a
kiosk session links *out* to those rows by nullable FK instead of duplicating
the participant.

Data-minimisation posture (matches the WhatsApp rail): no raw face frames are
persisted. ``kiosk_biometric_metadata`` keeps only derived quality signals;
``kiosk_clinical_results`` keeps the triage summary encrypted at rest with
AES-256-GCM (ciphertext + 96-bit nonce + external ``key_id``); the cleartext
phone never lands here — it stays on the linked ``whatsapp_sessions`` row, which
the account-erasure flow already scrubs.

``kiosk_result_tokens`` backs the single-use, OTP-gated, 24h result portal: only
the SHA-256 of the URL token and an argon2 hash of the 4-digit OTP are stored,
with a bounded attempt counter to make the 10k OTP space non-brute-forceable.

Revision ID: 20260301_3100
Revises: 20260301_3000
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260301_3100"
down_revision: str | None = "20260301_3000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


KIOSK_SESSION_STATUS = postgresql.ENUM(
    "INITIATED",  # row created by the kiosk; QR shown, nobody linked yet
    "LINKED",  # an inbound WhatsApp message bound an MSISDN to the session
    "CONSENTED",  # the linked participant granted capture consent
    "CAPTURED",  # frames processed in-memory; derived metadata persisted
    "PROCESSING",  # a processing_jobs row is running the pipeline
    "COMPLETE",  # result encrypted + token minted + notification sent
    "EXPIRED",  # session token lapsed (inactivity / TTL) before completion
    "ABORTED",  # explicitly torn down (kiosk purge / participant withdrew)
    name="kiosk_session_status",
    create_type=False,
)


def upgrade() -> None:
    KIOSK_SESSION_STATUS.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------ #
    # kiosk_sessions — one row per terminal capture attempt.
    # ------------------------------------------------------------------ #
    op.create_table(
        "kiosk_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Physical terminal identifier (provisioned device id).
        sa.Column("kiosk_id", sa.String(64), nullable=False),
        # Deployment site / country — drives jurisdiction (NG->NDPA, ZW->CDPA,
        # ZA->POPIA) and the retention/consent copy, same as ``users.site_code``.
        sa.Column(
            "site_code",
            sa.String(16),
            nullable=False,
            server_default="DEFAULT",
        ),
        sa.Column(
            "status",
            KIOSK_SESSION_STATUS,
            nullable=False,
            server_default="INITIATED",
        ),
        # Short, single-use code embedded in the QR-prefilled WhatsApp text. The
        # webhook matches an inbound message to this session by this nonce.
        sa.Column("verification_nonce", sa.String(32), nullable=False),
        # Pseudonymous account anchored at consent (no PII). SET NULL so a
        # tombstoned user never cascade-deletes the separately-scrubbed session.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # The conversation row that carries the (erasable) cleartext phone.
        sa.Column(
            "whatsapp_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("whatsapp_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # The async job that runs the pipeline once frames are captured.
        sa.Column(
            "processing_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Hard expiry of the session token (kiosk inactivity + overall TTL).
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_kiosk_sessions_verification_nonce",
        "kiosk_sessions",
        ["verification_nonce"],
        unique=True,
    )
    # Drives the expiry reaper: sweep non-terminal sessions past expires_at.
    op.create_index(
        "ix_kiosk_sessions_status_expires_at",
        "kiosk_sessions",
        ["status", "expires_at"],
    )
    op.create_index("ix_kiosk_sessions_user_id", "kiosk_sessions", ["user_id"])
    op.create_index("ix_kiosk_sessions_kiosk_id", "kiosk_sessions", ["kiosk_id"])

    # ------------------------------------------------------------------ #
    # kiosk_biometric_metadata — derived quality signals ONLY (no frames).
    # ------------------------------------------------------------------ #
    op.create_table(
        "kiosk_biometric_metadata",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kiosk_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Composite acquisition quality in [0,1].
        sa.Column("signal_quality_index", sa.Float(), nullable=True),
        # Ambient illumination score from hidden-canvas pixel-intensity analysis.
        sa.Column("illumination_score", sa.Float(), nullable=True),
        # Fraction of the frame occupied by the face bounding box (gate: >0.40).
        sa.Column("face_bbox_ratio", sa.Float(), nullable=True),
        sa.Column(
            "frame_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "error_flags",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(signal_quality_index IS NULL OR "
            "(signal_quality_index >= 0 AND signal_quality_index <= 1)) AND "
            "(illumination_score IS NULL OR "
            "(illumination_score >= 0 AND illumination_score <= 1)) AND "
            "(face_bbox_ratio IS NULL OR "
            "(face_bbox_ratio >= 0 AND face_bbox_ratio <= 1))",
            name="ck_kiosk_biometric_metadata_scores_unit",
        ),
        sa.CheckConstraint(
            "frame_count >= 0",
            name="ck_kiosk_biometric_metadata_frame_count_nonneg",
        ),
    )
    op.create_index(
        "ix_kiosk_biometric_metadata_session_id",
        "kiosk_biometric_metadata",
        ["session_id"],
    )

    # ------------------------------------------------------------------ #
    # kiosk_clinical_results — triage summary encrypted at rest (AES-256-GCM).
    # ------------------------------------------------------------------ #
    op.create_table(
        "kiosk_clinical_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kiosk_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # AES-256-GCM ciphertext (includes the 128-bit auth tag) of the
        # serialized triage summary. Plaintext never touches the database.
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        # 96-bit GCM nonce, unique per encryption.
        sa.Column("encryption_nonce", sa.LargeBinary(), nullable=False),
        # Identifier of the externally-managed key version used (key rotation).
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_kiosk_clinical_results_session_id",
        "kiosk_clinical_results",
        ["session_id"],
        unique=True,
    )

    # ------------------------------------------------------------------ #
    # kiosk_result_tokens — single-use, OTP-gated, 24h secure-portal access.
    # ------------------------------------------------------------------ #
    op.create_table(
        "kiosk_result_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kiosk_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kiosk_clinical_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SHA-256 (hex) of the opaque URL token — the cleartext is sent once and
        # never stored, so a database read cannot reconstruct a portal link.
        sa.Column("token_hash", sa.String(128), nullable=False),
        # argon2 hash of the 4-digit OTP (second factor). Nullable until issued.
        sa.Column("otp_hash", sa.String(255), nullable=True),
        sa.Column(
            "otp_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "max_otp_attempts",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        # Single-use: set on first successful unlock; subsequent reads rejected.
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        # Hard expiry exactly 24h after generation.
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "otp_attempts >= 0 AND otp_attempts <= max_otp_attempts + 1",
            name="ck_kiosk_result_tokens_attempts_bounded",
        ),
    )
    op.create_index(
        "ix_kiosk_result_tokens_token_hash",
        "kiosk_result_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_kiosk_result_tokens_session_id",
        "kiosk_result_tokens",
        ["session_id"],
    )
    # Drives the token-expiry reaper.
    op.create_index(
        "ix_kiosk_result_tokens_expires_at",
        "kiosk_result_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_kiosk_result_tokens_expires_at", table_name="kiosk_result_tokens"
    )
    op.drop_index(
        "ix_kiosk_result_tokens_session_id", table_name="kiosk_result_tokens"
    )
    op.drop_index(
        "ix_kiosk_result_tokens_token_hash", table_name="kiosk_result_tokens"
    )
    op.drop_table("kiosk_result_tokens")

    op.drop_index(
        "ix_kiosk_clinical_results_session_id",
        table_name="kiosk_clinical_results",
    )
    op.drop_table("kiosk_clinical_results")

    op.drop_index(
        "ix_kiosk_biometric_metadata_session_id",
        table_name="kiosk_biometric_metadata",
    )
    op.drop_table("kiosk_biometric_metadata")

    op.drop_index("ix_kiosk_sessions_kiosk_id", table_name="kiosk_sessions")
    op.drop_index("ix_kiosk_sessions_user_id", table_name="kiosk_sessions")
    op.drop_index(
        "ix_kiosk_sessions_status_expires_at", table_name="kiosk_sessions"
    )
    op.drop_index(
        "ix_kiosk_sessions_verification_nonce", table_name="kiosk_sessions"
    )
    op.drop_table("kiosk_sessions")

    op.execute("DROP TYPE IF EXISTS kiosk_session_status")
