"""Integration-test harness — the live ASGI app against a REAL PostgreSQL.

These tests deliberately run on PostgreSQL, not an in-memory SQLite double, so
they catch dialect-specific behaviour that SQLite would mask: native ``ENUM``
type creation (the source of a real migration double-create bug), ``JSONB`` /
``ARRAY`` columns, ``gen_random_uuid()`` server defaults, and partial unique
indexes.

Database selection (in priority order):

1. ``DATABASE_URL`` is set in the environment (CI with a ``postgres`` service
   container) — use it, and derive the synchronous Alembic DSN from it.
2. Otherwise spin an ephemeral, self-contained PostgreSQL via ``pgserver``
   (bundled binaries on a unix socket) so ``pytest`` "just works" locally with
   no Docker daemon required. The instance is torn down at session end.

Migrations are applied once per session with ``alembic upgrade head`` so the
schema under test is exactly what ships.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient

_API_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _set_default(key: str, value: str) -> None:
    os.environ.setdefault(key, value)


# Deterministic, non-production app secrets. Set at import time so the first
# (lru_cached) ``get_settings()`` — which happens when the app is imported in
# the ``client`` fixture — observes them. ``api_env=test`` also disables the
# production-secret guard in ``get_settings``.
_set_default("API_ENV", "test")
_set_default("JWT_SECRET_KEY", "test-jwt-secret-" + "0" * 40)
_set_default("INTERNAL_SERVICE_TOKEN", "test-internal-token-" + "0" * 24)
_set_default("PSEUDO_SALT", "test-pseudo-salt-" + "0" * 40)

# Prefer the per-disease multi-head checkpoint; fall back to the legacy
# single-head demo checkpoint if the newer artifact is absent. (The legacy
# checkpoint no longer satisfies the multi-head loader and will gracefully
# degrade to the rule-based per-disease backend.)
for _candidate in (
    _API_ROOT / "models" / "triage_edl_multihead_v1.pt",
    _API_ROOT / "models" / "triage_edl_v1_demo.pt",
):
    if _candidate.exists():
        _set_default("VICTUS_TRIAGE_MODEL_PATH", str(_candidate))
        break


def _socket_dir_from_uri(uri: str) -> str:
    """pgserver hands back a libpq URI like
    ``postgresql://postgres:@/postgres?host=/tmp/xxx`` — pull out the socket
    directory so we can build SQLAlchemy DSNs for both drivers.
    """
    return parse_qs(urlparse(uri).query)["host"][0]


@pytest.fixture(scope="session")
def _database() -> Iterator[None]:
    if os.environ.get("DATABASE_URL"):
        async_url = os.environ["DATABASE_URL"]
        os.environ.setdefault("ALEMBIC_DATABASE_URL", async_url.replace("+asyncpg", "+psycopg"))
        yield
        return

    pgserver = pytest.importorskip(
        "pgserver",
        reason=(
            "integration tests need a database: set DATABASE_URL to a Postgres "
            "instance, or `pip install pgserver` to auto-provision one"
        ),
    )
    import asyncio

    import asyncpg

    pgdata = tempfile.mkdtemp(prefix="victus_pgtest_")
    srv = pgserver.get_server(pgdata, cleanup_mode="stop")
    socket_dir = _socket_dir_from_uri(srv.get_uri())

    async def _bootstrap() -> None:
        conn = await asyncpg.connect(host=socket_dir, user="postgres", database="postgres")
        try:
            if not await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = 'victus'"):
                await conn.execute("CREATE ROLE victus WITH LOGIN SUPERUSER PASSWORD 'victus'")
            if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'victus'"):
                await conn.execute("CREATE DATABASE victus OWNER victus")
        finally:
            await conn.close()

    asyncio.run(_bootstrap())

    os.environ["DATABASE_URL"] = f"postgresql+asyncpg://victus:victus@/victus?host={socket_dir}"
    os.environ["ALEMBIC_DATABASE_URL"] = (
        f"postgresql+psycopg://victus:victus@/victus?host={socket_dir}"
    )
    try:
        yield
    finally:
        srv.cleanup()
        shutil.rmtree(pgdata, ignore_errors=True)


@pytest.fixture(scope="session")
def _migrated(_database: None) -> Iterator[None]:
    """Apply every Alembic migration to the (empty) test database once."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_API_ROOT,
        check=True,
        env=os.environ.copy(),
    )
    yield


@pytest.fixture(scope="session")
def client(_migrated: None) -> Iterator[TestClient]:
    """A ``TestClient`` bound to the real app + real Postgres.

    Session-scoped: the app and its connection pool are created once. Tests
    isolate themselves by registering uniquely-named users rather than by
    truncating tables, so a shared client is safe and fast.
    """
    from fastapi.testclient import TestClient

    from victus_api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def require_triage_model() -> None:
    """Skip EDL-dependent assertions when the shipped checkpoint is absent
    (e.g. a CI checkout without the model artifact). Safety-override and
    plausibility-of-input behaviour is exercised separately and does not need
    the model."""
    if "VICTUS_TRIAGE_MODEL_PATH" not in os.environ:
        pytest.skip("triage EDL checkpoint not present in this environment")
