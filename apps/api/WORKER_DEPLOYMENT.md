# Deploying the WhatsApp capture worker

The WhatsApp rail has **two** runtime pieces:

1. The **webhook** — part of the API process (`apps/api`); it just verifies the
   Meta signature, advances the conversation, writes a `processing_jobs` row, and
   returns 200. Deploy it with the API ([DEPLOYMENT.md](DEPLOYMENT.md)).
2. The **worker** (this doc) — a **separate process** that claims queued jobs,
   downloads the video from Meta, extracts rPPG, runs the pipeline, persists the
   `ToiAssessment`, and sends the WhatsApp reply.

They share one PostgreSQL database (the queue). The worker does the heavy lifting
off the request path, so the webhook always answers Meta instantly.

> **The worker needs OpenCV.** Install the API with the `video` extra
> (`uv sync --extra video`, or add `opencv-python-headless` to the venv). The
> webhook/API itself does **not** need it (`cv2` is imported lazily).

---

## Two ways to run it

| Path | Command | When |
| --- | --- | --- |
| **A — cron (`--once`)** | drain the queue and exit, every minute | cPanel / any host with cron; no long-running process |
| **B — persistent (`--loop`)** | poll forever | a VPS / managed host (systemd, Docker, supervisor) |

Both reach the same conclusion; cron just adds up to ~1 minute of latency, which
is fine for an asynchronous check-up ("your results will arrive here shortly").
On shared cPanel — which throttles long-running processes — use **cron**. If the
API is already on a VPS (the realistic home for the FastAPI + Postgres backend),
co-locate the worker there as a **systemd** service.

---

## Environment

The worker reuses the app `Settings`, so it needs the **same** core env as the
API, plus WhatsApp send/fetch credentials and (optionally) worker tuning. Set
these in the cron environment, the systemd unit, or an env file you `source`.

**Shared with the API** (identical values):

| Variable | Value |
| --- | --- |
| `API_ENV` | `production` |
| `DATABASE_URL` | `postgresql+asyncpg://USER:PASS@HOST:5432/victus` (the API's DB) |
| `JWT_SECRET_KEY` / `INTERNAL_SERVICE_TOKEN` / `PSEUDO_SALT` | same as the API — the app refuses to boot in production with placeholder secrets, even though the worker doesn't use all of them functionally |

> The worker owns its own event loop, so — unlike the Passenger/WSGI API — it does
> **not** need `DB_DISABLE_POOL`. Leave normal pooling on.

**WhatsApp (worker side — media download + sending):**

| Variable | Value |
| --- | --- |
| `WHATSAPP_ACCESS_TOKEN` | Meta permanent token (download + send) |
| `WHATSAPP_PHONE_NUMBER_ID` | the sending number's id |
| `WHATSAPP_API_VERSION` | optional, defaults to `v21.0` |

(The webhook side additionally needs `WHATSAPP_VERIFY_TOKEN` + `WHATSAPP_APP_SECRET`; set all four everywhere for simplicity.)

**Worker tuning (all optional — sensible defaults shown):**

| Variable | Default | Meaning |
| --- | --- | --- |
| `WORKER_BATCH_SIZE` | `5` | max jobs claimed per poll |
| `WORKER_MAX_ATTEMPTS` | `3` | transient-failure retries before FAILED |
| `WORKER_RETRY_BACKOFF_S` | `60` | base backoff × attempt number |
| `WORKER_POLL_INTERVAL_S` | `5` | loop-mode sleep between empty polls |
| `WORKER_MEDIA_DIR` | `var/whatsapp-media` | scratch dir for the downloaded video — set an **absolute, writable** path |
| `WORKER_PURGE_MEDIA` | `true` | delete the raw video after extraction (keep `true`) |

---

## Path A — cPanel cron (`--once`)

1. Install the worker's deps into the API's virtualenv, **with OpenCV**:
   ```bash
   # in the cPanel Python App virtualenv (or your venv)
   pip install -r requirements-cpanel.txt opencv-python-headless
   ```
2. Create a writable media scratch dir and set `WORKER_MEDIA_DIR` to it, e.g.
   `~/victus-media` (`mkdir -p ~/victus-media`).
3. cPanel → **Cron Jobs** → add a **once-per-minute** job. Put the env inline (cron
   has a bare environment), or `source` an env file:
   ```
   * * * * * cd ~/victus-api && . ~/victus-api/worker.env && \
     ~/virtualenv/victus-api/3.12/bin/python -m victus_api.worker --once \
     >> ~/victus-worker.log 2>&1
   ```
   where `~/victus-api/worker.env` exports the variables from the tables above
   (`export DATABASE_URL=...`, `export WHATSAPP_ACCESS_TOKEN=...`, etc.) and
   `PYTHONPATH=src`.
4. Watch `~/victus-worker.log` — each run logs `worker_run_once_complete handled=N`.

`--once` claims a batch (`FOR UPDATE SKIP LOCKED`), processes it, and exits, so
overlapping cron runs never double-process a job.

---

## Path B — VPS / systemd (`--loop`)

```ini
# /etc/systemd/system/victus-worker.service
[Unit]
Description=Victus WhatsApp capture worker
After=network-online.target

[Service]
WorkingDirectory=/opt/victus/apps/api
Environment=PYTHONPATH=/opt/victus/apps/api/src
EnvironmentFile=/opt/victus/worker.env          # the variables above
ExecStart=/opt/victus/.venv/bin/python -m victus_api.worker --loop
Restart=always
RestartSec=5
User=victus

[Install]
WantedBy=multi-user.target
```

```bash
# one-time
python3.12 -m venv /opt/victus/.venv && . /opt/victus/.venv/bin/activate
pip install -r /opt/victus/apps/api/requirements-cpanel.txt opencv-python-headless
sudo systemctl enable --now victus-worker
sudo journalctl -u victus-worker -f         # live logs
```

`--loop` polls continuously (`WORKER_POLL_INTERVAL_S` between empty polls), so
captures are processed within seconds. systemd restarts it on crash/reboot. A
stale-job reaper recovers any job whose worker died mid-processing.

---

## Local end-to-end test (no Meta, no real video needed)

`--local-media` treats `media_id` as a **local file path** and prints replies to
stdout instead of calling Meta — so you can exercise the whole worker without
WhatsApp credentials:

```bash
# enqueue a job whose media_id is a path to any local .mp4, then:
PYTHONPATH=src python -m victus_api.worker --once --local-media
```

The unit + integration suites (`tests/test_worker_processor.py`,
`tests/test_video_extract.py`, `tests/integration/test_whatsapp_webhook.py`) cover
the extraction → vitals → persistence path against synthetic clips and real
Postgres.

## Verify in production

1. Send a real WhatsApp check-up through to the video step (a `processing_jobs`
   row appears, `status=QUEUED`).
2. Within a minute (cron) / seconds (loop), the row moves to `SUCCEEDED` (or
   `REJECTED` for a poor capture) and the participant receives the reply.
3. A `toi_assessments` row is written for the participant's anchored user, with a
   `PATHWAY_B_ASSESSMENT_COMPLETED` audit entry.

## Troubleshooting

- **Jobs stay QUEUED** — the worker isn't running, or its `DATABASE_URL` points at
  a different DB than the webhook. Confirm both share one database.
- **`ModuleNotFoundError: cv2`** — the worker venv is missing the `video` extra;
  `pip install opencv-python-headless`.
- **Jobs reach FAILED after retries** — check the worker log for
  `capture_extract_failed` / `capture_pipeline_failed`; usually a bad download
  (wrong `WHATSAPP_ACCESS_TOKEN`) or an unreadable video.
- **No reply sent** — `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` missing
  or wrong; the vitals still persist, only the outbound message fails.
- **Worker won't boot in production** — a placeholder `JWT_SECRET_KEY` /
  `INTERNAL_SERVICE_TOKEN` / `PSEUDO_SALT`; set the real values (same as the API).
