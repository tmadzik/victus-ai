"""Application settings, sourced from environment via pydantic-settings.

All settings are validated at import-time; a misconfigured deployment fails
fast instead of degrading silently in production.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Well-known development AES-256 key (32 zero bytes, hex). The production guard
# refuses to boot if the kiosk key is still this placeholder.
KIOSK_DEV_ENCRYPTION_KEY = "00" * 32


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return here.parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_repo_root() / ".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_env: Literal["development", "staging", "production", "test"] = "development"
    # Binding all interfaces is intentional: the API runs inside a container
    # and exposure is controlled at the proxy/firewall, not the process.
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000
    api_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Expose experimental, not-yet-validated TOI biomarkers (HRV, stress index)
    # in API responses. OFF by default: the product must not present an
    # unvalidated estimate as a measurement. Enable only for research/validation.
    toi_expose_experimental_biomarkers: bool = False

    # --- Clinical-claims gate --------------------------------------------------
    # The platform must not present a model-derived NCD risk state as an
    # actionable clinical result until the model has passed prospective
    # validation on the deployed population (docs/PROSPECTIVE_VALIDATION_PLAN.md).
    # The gate is OPEN only when BOTH are set: the operator explicitly enables
    # clinical claims AND names the validated model card that authorises them.
    # Default CLOSED → the platform runs as an honest research demonstrator.
    clinical_claims_enabled: bool = False
    # Identifier / path / attestation of the validated model card authorising
    # clinical claims. Presence is required for the gate to open — enabling the
    # flag alone is not enough.
    clinical_claims_model_card: str | None = None

    # Deployment site / country for this instance (e.g. "ZW", "NG"). Each pilot
    # runs as its own deployment; new participants and research cases are stamped
    # with it for residency partitioning and per-site analytics/calibration.
    site_code: str = Field(default="DEFAULT", max_length=16)

    database_url: str = Field(
        default="postgresql+asyncpg://victus:victus_dev_only_change_me@localhost:5432/victus",
        description="Async SQLAlchemy DSN (asyncpg).",
    )
    alembic_database_url: str = Field(
        default="postgresql+psycopg://victus:victus_dev_only_change_me@localhost:5432/victus",
        description="Sync DSN for Alembic.",
    )
    db_disable_pool: bool = Field(
        default=False,
        description=(
            "Use SQLAlchemy NullPool (a fresh connection per request) instead of "
            "a persistent connection pool. Set this on WSGI/Passenger hosts "
            "(cPanel 'Setup Python App'), where an ASGI adapter runs each request "
            "on a new event loop — a pooled asyncpg connection would be bound to "
            "a stale loop and raise 'attached to a different loop'. Leave off for "
            "uvicorn/VPS deployments, which keep one loop and benefit from pooling."
        ),
    )

    jwt_secret_key: SecretStr = Field(
        default=SecretStr("dev_jwt_secret_replace_with_openssl_rand_hex_32_xxxxxxxxxxxxxxxx"),
        description="HMAC secret for JWT signing — MUST be overridden in non-dev environments.",
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    jwt_refresh_ttl_seconds: int = Field(default=2_592_000, ge=3_600)

    cors_allowed_origins: str = "http://localhost:3000"

    internal_service_token: SecretStr = Field(
        default=SecretStr("dev_internal_token_replace_with_openssl_rand_hex_32_xxxxxxxx"),
        description="Shared secret for privileged Next.js -> FastAPI calls.",
    )

    pseudo_salt: SecretStr = Field(
        default=SecretStr(
            "dev_pseudo_salt_replace_with_openssl_rand_hex_32_xxxxxxxxxxxxx"
        ),
        description=(
            "Per-deployment salt for one-way pseudonymisation of subject ids "
            "during anonymisation. Treat as a long-lived deployment secret — "
            "rotating it breaks the link to pre-rotation pseudonyms."
        ),
    )

    notify_webhook_url: str | None = Field(
        default=None,
        description=(
            "Optional Slack-compatible incoming-webhook URL. When set, "
            "governance approval-request notifications are POSTed here in "
            "addition to the persisted in-app notifications. Best-effort: "
            "delivery failures never block the erasure flow."
        ),
    )
    notify_webhook_timeout_s: float = Field(default=4.0, ge=0.5, le=30.0)
    # Base URL the in-app deep links resolve against in webhook payloads. Also
    # the host the kiosk secure-result portal links resolve against.
    web_app_base_url: str = "http://localhost:3000"

    # --- Mobile Clinic Gateway (kiosk rail) ----------------------------------
    # AES-256 key for the kiosk clinical-result envelope, supplied externally
    # (secrets file / host env) — 64 hex chars or base64 decoding to 32 bytes.
    # MUST be overridden outside development; the prod guard rejects the default.
    kiosk_encryption_key: SecretStr = Field(
        default=SecretStr(KIOSK_DEV_ENCRYPTION_KEY),
        description="External AES-256-GCM key for kiosk result payloads.",
    )
    # Version label for the active key, stamped on every ciphertext so a future
    # rotation can still resolve which key decrypts an older row.
    kiosk_key_id: str = Field(default="kiosk-dev-1", max_length=64)
    # Overall kiosk session lifetime (the 30s inactivity purge is a frontend
    # concern; this is the server-side hard ceiling on an unfinished session).
    kiosk_session_ttl_seconds: int = Field(default=900, ge=60, le=3_600)
    # Secure-result token lifetime — the spec mandates exactly 24h.
    kiosk_result_token_ttl_seconds: int = Field(
        default=86_400, ge=300, le=604_800
    )
    # Wrong-OTP attempts before the result token is permanently locked. Bounds
    # the 10k 4-digit space to a non-brute-forceable handful of tries.
    kiosk_otp_max_attempts: int = Field(default=5, ge=3, le=10)

    @field_validator("database_url")
    @classmethod
    def _validate_async_dsn(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")
        return value

    @field_validator("alembic_database_url")
    @classmethod
    def _validate_sync_dsn(cls, value: str) -> str:
        if not value.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("ALEMBIC_DATABASE_URL must use the postgresql+psycopg driver")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.api_env == "production"

    @property
    def clinical_claims_active(self) -> bool:
        """Clinical claims are authorised only when explicitly enabled AND a
        validated model card is named. Either alone leaves the gate closed."""
        return self.clinical_claims_enabled and bool(self.clinical_claims_model_card)

    def assert_safe_for_production(self) -> None:
        """Refuse to boot in production with dev-only secrets."""
        if not self.is_production:
            return
        if "replace" in self.jwt_secret_key.get_secret_value().lower():
            raise RuntimeError("JWT_SECRET_KEY is still the development placeholder")
        if "replace" in self.internal_service_token.get_secret_value().lower():
            raise RuntimeError("INTERNAL_SERVICE_TOKEN is still the development placeholder")
        if "replace" in self.pseudo_salt.get_secret_value().lower():
            raise RuntimeError("PSEUDO_SALT is still the development placeholder")
        if self.kiosk_encryption_key.get_secret_value() == KIOSK_DEV_ENCRYPTION_KEY:
            raise RuntimeError("KIOSK_ENCRYPTION_KEY is still the development placeholder")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        settings.assert_safe_for_production()
    return settings
