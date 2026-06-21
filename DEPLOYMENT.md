# Victus AI — cPanel launch runbook

The master, ordered runbook. Each step links to the deployable's own guide for
detail; this page is the **sequence**, the **shared-secret map**, and the
**host-capability checklist** you confirm before you start.

There are four deployables:

| # | Piece | Hostname | Host feature needed | Guide |
| - | --- | --- | --- | --- |
| 1 | **API** (FastAPI + WhatsApp webhook) | `api.victusdata.com` | **PostgreSQL** + **Setup Python App** + **Python 3.12** | [apps/api/DEPLOYMENT.md](apps/api/DEPLOYMENT.md) |
| 2 | **Worker** (WhatsApp capture) | (no hostname) | Cron + Python 3.12 + the API's DB | [apps/api/WORKER_DEPLOYMENT.md](apps/api/WORKER_DEPLOYMENT.md) |
| 3 | **Web app** (clinical) | `app.victusdata.com` | **Setup Node.js App** (Node 20+) | [apps/web/DEPLOYMENT.md](apps/web/DEPLOYMENT.md) |
| 4 | **Marketing site** | `www.victusdata.com` | Setup Node.js App (Node 20+) | [apps/marketing/DEPLOYMENT.md](apps/marketing/DEPLOYMENT.md) |

> **The gate:** pieces 3 & 4 run on any cPanel with Node 20. Pieces 1 & 2 need
> **PostgreSQL + Python 3.12** — the code will **not** run on Python 3.8. Confirm
> this with your host **first** (checklist at the bottom). If the plan can't
> offer it, run the API + worker on a small VPS and keep cPanel for the two
> front-ends — nothing else changes.

> **MVP launch profile — host has PostgreSQL + Python 3.12 but no background
> process/cron:** deploy pieces **1, 3, 4 (API, web, marketing)** and **skip the
> worker (piece 2 / Step 4)**. The worker is the only deployable that is a
> background job; the API is request-driven under Passenger, so "no background
> process" does **not** block it. Skipping the worker turns the WhatsApp rail off
> — inbound messages would queue but never get a reply, so it's all-or-nothing
> and stays off until you have either cron (worker Path A) or a small VPS for the
> worker alone. Everything the MVP demonstrates — web triage, in-browser TOI/rPPG,
> and the `/research` console — runs without it.

---

## Step 0 — Confirm host capabilities

Run the **[Send-to-host checklist](#send-to-host-checklist)** at the bottom. Do
not start until you have a yes on PostgreSQL + Python 3.12, or a decision to put
the API/worker on a VPS. A **no on cron/background process** is _not_ a blocker —
it only defers the worker; see the **MVP launch profile** callout above.

## Step 1 — DNS + subdomains (one-time)

In cPanel → **Domains**:
- `www.victusdata.com` → marketing site (Node app, step 5).
- `app.victusdata.com` → clinical web app (Node app, step 6).
- `api.victusdata.com` → API (Python app, step 3).
- **Apex → www**: a permanent (301) redirect `victusdata.com → https://www.victusdata.com`.

## Step 2 — Generate the shared secrets (once)

Generate these **once** and reuse the exact values where the map below says so.

```bash
openssl rand -hex 32   # JWT_SECRET_KEY
openssl rand -hex 32   # INTERNAL_SERVICE_TOKEN   (API ↔ web ↔ worker)
openssl rand -hex 32   # PSEUDO_SALT              (do NOT rotate later)
openssl rand -base64 48 # AUTH_SECRET             (web only)
```

WhatsApp values (`WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`,
`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`) come from Meta once business
verification completes — leave them blank for an initial launch without WhatsApp.

## Step 3 — API + database

Follow [apps/api/DEPLOYMENT.md](apps/api/DEPLOYMENT.md): create the PostgreSQL DB,
create the Python App (`passenger_wsgi.py`, Python 3.12), upload, `pip install -r
requirements-cpanel.txt`, set env, `alembic upgrade head`, restart. **Done when
`https://api.victusdata.com/readyz` returns ready.**

## Step 4 — Worker (cron)

Follow [apps/api/WORKER_DEPLOYMENT.md](apps/api/WORKER_DEPLOYMENT.md) — Path A
(cron `--once` every minute). Install the `video` extra (`opencv-python-headless`)
into the API venv. Skip this step entirely if you're launching without WhatsApp.

## Step 5 — Clinical web app

Build locally and upload:
```bash
NEXT_PUBLIC_API_BASE_URL=https://api.victusdata.com \
  pnpm --filter @victus/web build:cpanel    # → apps/web/dist-cpanel/victus-web-cpanel.zip
```
Then follow [apps/web/DEPLOYMENT.md](apps/web/DEPLOYMENT.md): Node.js App on
`app.victusdata.com`, upload/extract, set env, start. **Deploy this AFTER the
API** (it needs the API reachable).

## Step 6 — Marketing site

```bash
NEXT_PUBLIC_APP_URL=https://app.victusdata.com \
  pnpm --filter @victus/marketing build:cpanel
```
Then [apps/marketing/DEPLOYMENT.md](apps/marketing/DEPLOYMENT.md): Node.js App on
`www.victusdata.com`, upload/extract, SMTP env, start.

## Step 7 — TLS + go-live verification

1. cPanel → **Domains** → **Force HTTPS Redirect** on all three hostnames (the web
   app's camera/rPPG needs HTTPS).
2. Verify:
   - `curl https://api.victusdata.com/healthz` → `{"status":"ok"}`
   - `curl https://api.victusdata.com/readyz` → ready (DB reachable)
   - `https://www.victusdata.com` loads; the pilot form sends an email.
   - `https://app.victusdata.com` — register, sign in, run a Pathway A assessment
     (proves web → API → DB). A clinician opens **/research** and records a case.
   - If WhatsApp is live: send a check-up to the number; within ~1 min the worker
     replies with vitals.

---

## Shared-secret map (what must match what)

The #1 cause of a broken deploy is a secret that doesn't match across processes.

| Variable | API (Python app) | Worker (cron) | Web (Node app) | Must be identical across |
| --- | :-: | :-: | :-: | --- |
| `DATABASE_URL` (asyncpg) | ✅ | ✅ | — | API + worker (same DB) |
| `ALEMBIC_DATABASE_URL` (psycopg) | ✅ | — | — | — |
| `JWT_SECRET_KEY` | ✅ | ✅ | — | API + worker |
| `INTERNAL_SERVICE_TOKEN` | ✅ | ✅ | ✅ | **API + worker + web** |
| `PSEUDO_SALT` | ✅ | ✅ | — | API + worker (never rotate) |
| `AUTH_SECRET` | — | — | ✅ | web only |
| `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | ✅ | — | — | API webhook |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | — | ✅ | — | worker |
| `DB_DISABLE_POOL=1` | ✅ | — | — | API only (Passenger/WSGI) |
| `NEXT_PUBLIC_API_BASE_URL` | — | — | build-time | baked into the web bundle |
| `INTERNAL_API_BASE_URL`, `AUTH_URL`, `AUTH_TRUST_HOST=true` | — | — | ✅ | web runtime |

If `INTERNAL_SERVICE_TOKEN` differs between web and API, every clinical action
fails with 401/403. If `DATABASE_URL` differs between API and worker, WhatsApp
jobs queue but never process.

---

## Send-to-host checklist

> Copy/paste this to your hosting provider. The first three answers decide
> whether the API runs on cPanel or needs a small VPS.

```
We're deploying a web platform on our cPanel plan and need to confirm a few
capabilities:

1. Does this plan include PostgreSQL? (We need PostgreSQL 13+, not just MySQL.)
   - Is there a "PostgreSQL Databases" icon in cPanel?

2. Does cPanel offer "Setup Python App" (Phusion Passenger), and which Python
   versions are available in the selector? We require Python 3.12 (3.10 minimum).
   - If 3.12 isn't listed, can it be enabled for our account?

3. Can a long-running OR cron-driven background Python process run on this plan?
   (A once-per-minute cron job is sufficient.)

4. Does cPanel offer "Setup Node.js App" with Node.js 20 or newer? (For two
   front-end apps.)

5. Can we create subdomains (www, app, api) and enable Force HTTPS / AutoSSL on
   each?

6. Any limits we should know about: max processes, RAM per app, inode/disk
   quota, or restrictions on installing Python packages (numpy, scipy, opencv)
   via pip into the app's virtualenv?
```

**If the answer to #1 or #2 is no** (e.g. PostgreSQL unavailable or Python caps at
3.8): keep marketing + web on cPanel and put the **API + worker on a ~$5–10/mo
VPS** with managed Postgres (see Path B in [apps/api/DEPLOYMENT.md](apps/api/DEPLOYMENT.md)).
The web app only needs the API reachable over HTTPS — it doesn't care where it
lives.
