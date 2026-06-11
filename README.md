# Victus AI

[![CI](https://github.com/tmadzik/victus-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/tmadzik/victus-ai/actions/workflows/ci.yml)

Dual-pathway NCD risk prediction and Transdermal Optical Imaging biomarker platform engineered for clinical-validation deployment in Sub-Saharan African settings.

- **Pathway A — 3B-Triage:** Non-clinical NCD risk screening (Obesity / Hypertension / Diabetes) via tape-measure inputs and symptom audit. Dirichlet-EDL classifier with a gradient-reversal domain adversary trained to be invariant across `{CLINICAL_GRADE, CHW_TAPE_MEASURE, SYNTHETIC}` measurement provenance — tape-measure inputs collected by community health workers behave the same as clinical-grade inputs by construction. Epistemic/aleatoric uncertainty drives a strict GREEN / YELLOW / RED state machine. Hard-coded deterministic safety overrides (polydipsia, blurred vision, non-healing foot sores) bypass the network and escalate to RED.
- **Pathway B — TOI:** Transdermal Optical Imaging + rPPG biomarker extraction (HR, RR, BP, HRV, Stress, CVD risk, Stroke risk, BMI) tuned for Fitzpatrick III–VI via CHROM / POS chrominance pipelines.

## Architecture

```
.
├── apps/
│   ├── web/                Clinical app — app.victusdata.com (Next.js 15, App Router, RSC, TS strict, Tailwind v4, Auth.js v5)
│   ├── marketing/          Marketing site — www.victusdata.com (Next.js 15, fully static SSG, zero auth/PHI)
│   └── api/                FastAPI (Python 3.12, SQLAlchemy 2.x async, Pydantic v2, PyTorch)
├── packages/
│   ├── contracts/          Shared DTO + role/consent enums (TS)
│   └── ui/                 Shared design system — tokens (styles.css) + primitives consumed by web and marketing
├── infra/
│   └── docker-compose.yml  Postgres + (later) inference runtime
└── _legacy/                Archived pre-rebuild static scaffold
```

The marketing site and the clinical app are deployed independently (separate domains, separate pipelines) but share one visual language through `@victus/ui`: design tokens live in `packages/ui/src/styles.css` and base primitives (Button, Card, Input, Label, Badge, Alert) are imported from `@victus/ui` by both apps. Auth cookies are scoped strictly to the app subdomain — the marketing site carries no authentication and no clinical data.

The marketing site deploys to cPanel as a self-contained Node.js bundle (`pnpm --filter @victus/marketing build:cpanel`) — see [apps/marketing/DEPLOYMENT.md](apps/marketing/DEPLOYMENT.md). Pilot-request leads are forwarded via SMTP and/or a CRM webhook (`SMTP_*`, `LEAD_NOTIFY_*`, `CRM_WEBHOOK_*` in `.env.example`).

Authentication is FastAPI-owned (argon2id + JWT access/refresh + audit log). Auth.js acts as the Next.js-side session container, proxying credentials to `/auth/login` and forwarding the access token to FastAPI on subsequent requests, refreshing transparently when the access token nears expiry.

## Prerequisites

- Node.js ≥ 20.11
- pnpm ≥ 9 (`corepack enable && corepack prepare pnpm@9.12.3 --activate`)
- Python ≥ 3.12 with [`uv`](https://docs.astral.sh/uv/) (`pipx install uv`)
- Docker Desktop (for local Postgres)

## First-time setup

```bash
cp .env.example .env
# Generate secrets and patch .env:
#   JWT_SECRET_KEY      = openssl rand -hex 32
#   INTERNAL_SERVICE_TOKEN = openssl rand -hex 32
#   AUTH_SECRET         = openssl rand -base64 32

pnpm install
(cd apps/api && uv sync)

pnpm db:up
pnpm api:migrate
```

## Run

```bash
# Terminal 1 — FastAPI
pnpm api:dev          # http://localhost:8000  (Swagger UI: /docs)

# Terminal 2 — Next.js (runs both: clinical app + marketing site)
pnpm dev              # web: http://localhost:3000 · marketing: http://localhost:3001
```

## Verify

See `apps/api/README.md` for backend health checks and the end-of-milestone smoke test in this README's CHANGELOG.

## Security & compliance notes

- POPIA (South Africa) and HIPAA-aligned audit logging on every auth + pathway entry.
- argon2id for password hashing (OWASP recommended).
- JWT access tokens short-lived (15 min); refresh tokens rotate on use and are hashed at rest.
- HTTPS-only cookies, `SameSite=Lax`, CSRF via SameSite + Auth.js session token rotation.
- TOI camera capture (Pathway B) is gated on explicit consent and HTTPS (browser MediaStream API requirement).
