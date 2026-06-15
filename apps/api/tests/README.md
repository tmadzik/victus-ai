# API tests

Black-box **integration tests** that run the live FastAPI app against a **real
PostgreSQL** database — not an in-memory SQLite double. Running on Postgres is
deliberate: it catches dialect-specific behaviour that SQLite masks (native
`ENUM` type creation, `JSONB`/`ARRAY` columns, `gen_random_uuid()` server
defaults, partial unique indexes).

## Running

```bash
cd apps/api
uv run pytest                      # or: python -m pytest
```

No database setup is required locally. If `DATABASE_URL` is **not** set, the
test harness (`tests/conftest.py`) auto-provisions an ephemeral PostgreSQL via
[`pgserver`](https://pypi.org/project/pgserver/) (bundled binaries on a unix
socket, no Docker), applies every Alembic migration, and tears it down at the
end of the session.

To run against an existing database instead, export both DSNs:

```bash
export DATABASE_URL="postgresql+asyncpg://victus:victus@localhost:5432/victus"
export ALEMBIC_DATABASE_URL="postgresql+psycopg://victus:victus@localhost:5432/victus"
uv run pytest
```

CI (`.github/workflows/ci.yml`) sets `DATABASE_URL` to a `postgres:16` service
container, so the same tests run unchanged.

## Coverage

| Suite | What it locks in |
|-------|------------------|
| `test_pathway_a.py` | register / login / **JWT refresh rotation**, consent gating, **per-disease EDL risk assessment** (one Dirichlet + uncertainty per NCD, `overall_state` = worst of three, independent weighting), **deterministic safety override → RED with disease routing**, input-plausibility flags, history persistence |
| `test_pathway_b.py` | rPPG/TOI heart-rate recovery from a synthetic capture, study subject/session lifecycle, **6-pair calibration Bland-Altman** agreement, governance **maker-checker** erasure (segregation of duties, erased account can't authenticate), notification read lifecycle |

The EDL assertions skip automatically (`require_triage_model` fixture) if no
trained checkpoint is present (`models/triage_edl_multihead_v1.pt`, falling back
to `models/triage_edl_v1_demo.pt`); the safety-override and per-disease-shape
paths run regardless against the rule-based per-disease backend.

## Markers

`@pytest.mark.integration` tags every test here (enforced via
`--strict-markers`). Select or deselect with `-m integration` /
`-m "not integration"`.
