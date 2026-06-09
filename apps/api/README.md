# victus-api

FastAPI backend for Victus AI.

## Layout

```
src/victus_api/
├── main.py             ASGI app factory + middleware + routers
├── config.py           Pydantic Settings (env-driven, fail-fast)
├── core/
│   ├── logging.py      structlog config
│   ├── deps.py         FastAPI dependency providers
│   └── exceptions.py   Domain exceptions + handlers
├── db/
│   ├── base.py         Declarative base
│   ├── session.py      Async engine + session factory
│   └── models.py       User, RefreshToken, ConsentRecord, AuditLog
├── auth/
│   ├── security.py     argon2id, JWT access + refresh, hashing utilities
│   ├── schemas.py      Pydantic v2 DTOs
│   ├── service.py      register/login/refresh/logout
│   └── router.py       POST /auth/{register,login,refresh,logout}
├── users/              GET /users/me, PATCH /users/me/consents
├── audit/              write_audit() helper
└── pathways/           Pathway A/B entry endpoints (RBAC + consent guards)
```

## Setup

```bash
cd apps/api
uv sync                           # install runtime + dev deps
uv sync --extra ml                # add PyTorch for inference work
cp ../../.env.example ../../.env  # if not already
```

## Migrations

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "add foo"
```

## Run

```bash
uv run uvicorn victus_api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Verify

```bash
curl -fsS http://localhost:8000/healthz | jq
curl -fsS http://localhost:8000/readyz | jq
open http://localhost:8000/docs
```

## Train the Pathway A EDL checkpoint

Two training pipelines share a single CLI, dispatched on `--enable-dann`.

### Vanilla EDL (`architecture=sequential_v1`)

```bash
uv sync --extra ml
uv run python -m victus_api.training.cli \
  --data-dir "/path/to/datasets" \
  --output apps/api/models/triage_edl_v1.pt \
  --epochs 60 --seed 17
```

A flat MLP with Softplus evidence head and Sensoy Type-II ML loss.

### DANN-augmented EDL (`architecture=dann_v1`) — recommended demo checkpoint

```bash
uv run python -m victus_api.training.cli \
  --data-dir "/path/to/datasets" \
  --output apps/api/models/triage_edl_v1_demo.pt \
  --enable-dann --chw-noise-multiplier 4 --grl-gamma 10 \
  --no-class-balanced --focal-gamma 0 \
  --epochs 100 --annealing-epochs 200 --lr 1e-3 --seed 17 \
  --version "1.2.0-dann-jointsampler"
```

Shared feature extractor → (EDL task head) + (GRL → domain head). The CHW
domain is synthesised from `CLINICAL_GRADE` rows by injecting empirically-
grounded field-collection noise (height σ=0.5 cm + 1 cm quantization, waist
σ=2 cm + 1 cm quantization, BP σ=4 mmHg + 2 mmHg quantization). A joint
class × domain `WeightedRandomSampler` ensures the adversary gets meaningful
signal AND the task head sees balanced classes per batch.

Both pipelines fit a per-feature standard scaler on the training split, train
with KL annealing, and write a `.meta.json` sidecar containing feature
ordering, label mapping, scaler params, architecture identifier, training
hyperparameters, source/class/domain distributions, and per-epoch history.

### Activate at runtime

```bash
export VICTUS_TRIAGE_MODEL_PATH=apps/api/models/triage_edl_v1_demo.pt
pnpm api:dev
```

The runtime dispatches on `meta["architecture"]` (defaulting to
`sequential_v1` for backward compatibility with older sidecars) and refuses
to load any checkpoint whose feature ordering or label mapping disagrees with
the current `FEATURE_NAMES` / `RISK_CLASSES`. On any failure it falls back to
the rule-based predictor with a structured error log instead of silently
serving stale inference.
