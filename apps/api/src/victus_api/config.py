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

    database_url: str = Field(
        default="postgresql+asyncpg://victus:victus_dev_only_change_me@localhost:5432/victus",
        description="Async SQLAlchemy DSN (asyncpg).",
    )
    alembic_database_url: str = Field(
        default="postgresql+psycopg://victus:victus_dev_only_change_me@localhost:5432/victus",
        description="Sync DSN for Alembic.",
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
    # Base URL the in-app deep links resolve against in webhook payloads.
    web_app_base_url: str = "http://localhost:3000"

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if os.environ.get("PYTEST_CURRENT_TEST") is None:
        settings.assert_safe_for_production()
    return settings
