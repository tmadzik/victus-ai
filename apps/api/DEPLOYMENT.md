# Deploying the Victus API

The API is a **FastAPI (async ASGI) app backed by PostgreSQL**. That makes it the
hardest of the three deployables — it needs a real Postgres database and a way to
run a Python web process. Two supported paths:

| Path | When to use | Robustness |
| --- | --- | --- |
| **A — cPanel "Setup Python App" + PostgreSQL** | Your cPanel offers both a **PostgreSQL Databases** icon and a **Setup Python App** icon, and Python **3.12+** | Fine for a pilot (with caveats below) |
| **B — small VPS / managed host** | cPanel has no Postgres / no Python apps, or you want production-grade throughput | Recommended for production |

> **Check first (cPanel → main screen):** is there a **PostgreSQL Databases**
> icon, a **Setup Python App** icon, and is **Python 3.12+** offered? If any are
> missing, use Path B — don't fight it.

The API only serves data; the **web app** (`apps/web`) and **marketing site**
(`apps/marketing`) talk to it over HTTPS. Host it at e.g. `api.victusdata.com`.

---

## Path A — cPanel Python app + PostgreSQL

### A0. Caveats (read once)

- **No trained model.** `requirements-cpanel.txt` omits `torch` (too large for
  shared hosting). The API runs the **rule-based per-disease backend** — same
  response shape, clinically-grounded thresholds. To use the trained
  `dann_multihead_v1` checkpoint you'd `pip install torch` + set
  `VICTUS_TRIAGE_MODEL_PATH`, which realistically needs Path B.
- **Connect-per-request.** Passenger runs each request on a new event loop, so
  the API uses `NullPool` (no persistent pool) via `DB_DISABLE_POOL=1`. Correct
  and validated, just a little slower than pooled — fine for pilot traffic.

### A1. Create the PostgreSQL database

1. cPanel → **PostgreSQL Databases**.
2. **Create Database** — e.g. `victus` (cPanel prefixes it, so the real name
   becomes something like `cpaneluser_victus`).
3. **Create User** — e.g. `victususer` (becomes `cpaneluser_victususer`) with a
   strong password.
4. **Add the user to the database** with **ALL PRIVILEGES**.
5. Note the three values: full DB name, full user name, password. The host is
   `127.0.0.1` port `5432`. (PostgreSQL **13+** is recommended — the schema uses
   `gen_random_uuid()`, which is built in from PG13.)

### A2. Create the Python app

cPanel → **Setup Python App** → **Create Application**:
- **Python version:** 3.12 (or newer)
- **Application root:** `victus-api` (a folder in your home dir, _not_ in
  `public_html`)
- **Application URL:** `api.victusdata.com`
- **Application startup file:** `passenger_wsgi.py`
- **Application Entry point:** `application`

Create it, then **Stop** it while you upload.

### A3. Upload the code

Upload the contents of `apps/api/` into `~/victus-api/` so the folder contains:

```
passenger_wsgi.py
requirements-cpanel.txt
alembic.ini
alembic/            (migrations)
src/victus_api/...  (the app)
```

You do **not** need `tests/`, `.venv/`, `models/`, or `pyproject.toml`. Use
cPanel **File Manager** (upload a zip of those files and extract) or **Git
Version Control** if your host has it.

### A4. Install dependencies

In the **Setup Python App** screen, either use **"Run Pip Install"** with
`requirements-cpanel.txt`, **or** open the virtualenv terminal (the screen shows
a `source /home/.../bin/activate` command — run it) and:

```bash
cd ~/victus-api
pip install -r requirements-cpanel.txt
```

### A5. Configure environment variables

In the Python app screen, add these (generate each secret with
`openssl rand -hex 32`). Use the **full, prefixed** DB name/user from A1:

| Variable | Value |
| --- | --- |
| `API_ENV` | `production` |
| `DATABASE_URL` | `postgresql+asyncpg://cpaneluser_victususer:PASSWORD@127.0.0.1:5432/cpaneluser_victus` |
| `ALEMBIC_DATABASE_URL` | `postgresql+psycopg://cpaneluser_victususer:PASSWORD@127.0.0.1:5432/cpaneluser_victus` |
| `JWT_SECRET_KEY` | a 64-char random hex string |
| `INTERNAL_SERVICE_TOKEN` | a random string — **must match the web app's** |
| `PSEUDO_SALT` | a long random string (do not rotate — it anchors pseudonyms) |
| `CORS_ALLOWED_ORIGINS` | `https://app.victusdata.com` |
| `WEB_APP_BASE_URL` | `https://app.victusdata.com` |
| `DB_DISABLE_POOL` | `1` |

> `DATABASE_URL` must use the `postgresql+asyncpg://` driver and
> `ALEMBIC_DATABASE_URL` the `postgresql+psycopg://` driver — the app validates
> this at boot and refuses to start otherwise.

### A6. Create the schema (run migrations once)

In the virtualenv terminal, run Alembic with the sync DSN exported (the app-screen
env vars aren't always present in the terminal, so pass it inline):

```bash
cd ~/victus-api
export ALEMBIC_DATABASE_URL='postgresql+psycopg://cpaneluser_victususer:PASSWORD@127.0.0.1:5432/cpaneluser_victus'
PYTHONPATH=src alembic upgrade head
```

You should see each migration `20260301_0900 … 20260301_1900` apply in order.

### A7. Start and verify

1. **Restart** the app in the Python app screen.
2. cPanel → **Domains** → enable **Force HTTPS Redirect** for `api.victusdata.com`.
3. Check the endpoints:
   ```bash
   curl https://api.victusdata.com/healthz   # → {"status":"ok"} (liveness)
   curl https://api.victusdata.com/readyz    # → ready (verifies the DB)
   ```
   `/readyz` returning ready confirms the API ↔ PostgreSQL connection works.

### Updating

Upload the changed files, run any new migrations (A6), **Restart** the app. Env
vars persist.

---

## Path B — small VPS / managed host (recommended for production)

If cPanel can't host it, run the API on a ~$5/mo box (Railway, Render, Fly.io,
a DigitalOcean droplet, …) with managed Postgres. This keeps the normal async
connection pool (no `DB_DISABLE_POOL`) and lets you run the trained model.

Minimal recipe on a Linux box with Python 3.12 + Postgres reachable:

```bash
# one-time
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-cpanel.txt    # + `pip install torch` for the trained model
export DATABASE_URL='postgresql+asyncpg://USER:PASS@DBHOST:5432/victus'
export ALEMBIC_DATABASE_URL='postgresql+psycopg://USER:PASS@DBHOST:5432/victus'
export API_ENV=production JWT_SECRET_KEY=... INTERNAL_SERVICE_TOKEN=... PSEUDO_SALT=...
export CORS_ALLOWED_ORIGINS=https://app.victusdata.com
PYTHONPATH=src alembic upgrade head

# serve (behind nginx/Caddy doing TLS for api.victusdata.com)
PYTHONPATH=src uvicorn victus_api.main:app --host 127.0.0.1 --port 8000
```

Run uvicorn under a process manager (systemd, Docker, or the platform's own) so
it restarts on crash/reboot. Managed platforms (Railway/Render/Fly) do this for
you — point them at `apps/api`, set the env vars, use the start command
`uvicorn victus_api.main:app --host 0.0.0.0 --port $PORT`.

---

## Connecting the web app to the API

Whichever path you choose, set these on the **web** Node.js app
(see `apps/web/DEPLOYMENT.md`) so it reaches the API:

- `INTERNAL_API_BASE_URL = https://api.victusdata.com` (server-to-server)
- `NEXT_PUBLIC_API_BASE_URL = https://api.victusdata.com` (build-time)
- `INTERNAL_SERVICE_TOKEN` — **identical** to the API's value

If `INTERNAL_SERVICE_TOKEN` differs between the two, every privileged call fails
with 401/403.

## Troubleshooting

- **App won't start / 500 on every route** — check the Passenger log in the
  Python app screen. Common causes: a dependency failed to install (re-run A4),
  or an env var is missing (the app fails fast on a bad `DATABASE_URL` driver).
- **`attached to a different loop` errors** — `DB_DISABLE_POOL=1` is not set;
  add it (A5) and restart.
- **`/readyz` fails but `/healthz` is ok** — the app is up but can't reach
  Postgres: re-check the DB name/user/password and that the user has privileges
  on the database (A1).
- **CORS errors in the browser** — `CORS_ALLOWED_ORIGINS` must list the exact web
  origin (`https://app.victusdata.com`).
- **Migrations: `permission denied to create extension`** — your DB is older than
  PG13 or the user lacks rights; use PG13+ (the schema relies on the built-in
  `gen_random_uuid()`, no extension needed there).
