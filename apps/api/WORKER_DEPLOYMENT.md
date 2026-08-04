# Deploying the capture worker (WhatsApp + kiosk)

One background **worker** process drains **two** independent capture queues from
the shared PostgreSQL database:

- **WhatsApp** captures — downloads the video from Meta, extracts rPPG, runs the
  pipeline, persists the `ToiAssessment`, sends the WhatsApp reply.
- **Kiosk** captures — the kiosk terminal already extracted the rPPG signal
  in-browser (no video to download), so the worker runs the pipeline, persists
  the `ToiAssessment`, seals the result, mints a one-time code, and delivers the
  participant's secure-portal link + code over WhatsApp.

Both are handled by `python -m victus_api.worker` — a single `--once`/`--loop`
run processes each queue. **Scheduling this worker is what makes the kiosk rail
live in production**; without it, kiosk sessions sit `QUEUED` forever.

> The **webhook** (WhatsApp inbound) and the **kiosk gateway** API live in the
> API process (`apps/api`) and are deployed with it ([DEPLOYMENT.md](DEPLOYMENT.md)).
> This doc is only about the separate worker process. All three share one DB.

### OpenCV is only for the WhatsApp video rail

The WhatsApp path decodes video, so it needs OpenCV — install the API with the
`video` extra (`uv sync --extra video`, or `pip install opencv-python-headless`).
The **kiosk path needs no OpenCV** (the signal arrives pre-extracted) and neither
does the API/webhook (`cv2` is imported lazily). So a **kiosk-only** deployment —
the common case while WhatsApp verification is still pending — can skip OpenCV
entirely and still process every kiosk capture.

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
| `WHATSAPP_SEND_ENABLED` | **master switch — `false` by default.** While `false`, the worker never calls Meta (logs `whatsapp_rail_disabled` and uses safe no-network fakes: replies print to stdout, media downloads refuse). Set `true` only once Meta business verification is complete **and** the token/phone id below are set. |
| `WHATSAPP_ACCESS_TOKEN` | Meta permanent token (download + send) |
| `WHATSAPP_PHONE_NUMBER_ID` | the sending number's id |
| `WHATSAPP_API_VERSION` | optional, defaults to `v21.0` |
| `WHATSAPP_GRAPH_BASE_URL` | optional, defaults to `https://graph.facebook.com` |

> The rail is **off until you flip `WHATSAPP_SEND_ENABLED=true`**. If it is `true`
> but the token or phone id is missing, the worker logs `whatsapp_rail_misconfigured`
> and stays in the safe no-network mode rather than crashing.

(The webhook side additionally needs `WHATSAPP_VERIFY_TOKEN` + `WHATSAPP_APP_SECRET`; set all everywhere for simplicity.)

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

1. Install the worker's deps into the API's virtualenv. For a **kiosk-only**
   rollout, `requirements-cpanel.txt` is enough. Add OpenCV only when you turn on
   the WhatsApp video rail:
   ```bash
   # in the cPanel Python App virtualenv (or your venv)
   pip install -r requirements-cpanel.txt
   # WhatsApp video rail only:  pip install opencv-python-headless
   ```
2. Copy the env template and fill it in (see the tables above):
   ```bash
   cp apps/api/worker.env.example apps/api/worker.env   # then edit
   ```
   Set `PYTHON` to the venv's interpreter (e.g.
   `~/virtualenv/victus-api/3.12/bin/python`). For the WhatsApp rail, create a
   writable `WORKER_MEDIA_DIR` (`mkdir -p ~/victus-media`); the kiosk rail needs
   no scratch dir.
3. cPanel → **Cron Jobs** → add a **once-per-minute** job pointing at the wrapper
   (it loads `worker.env`, sets `PYTHONPATH`, and execs — no long inline command):
   ```
   * * * * * /home/USER/victus/apps/api/scripts/run-worker.sh --once >> ~/victus-worker.log 2>&1
   ```
   (Env lives in `worker.env`; override its location with `WORKER_ENV_FILE=...`.)
4. Watch `~/victus-worker.log` — each run logs
   `worker_run_once_complete whatsapp=N kiosk=M`.

`--once` claims a batch (`FOR UPDATE SKIP LOCKED`), processes it, and exits, so
overlapping cron runs never double-process a job.

---

## Path B — VPS / systemd (`--loop`)

```ini
# /etc/systemd/system/victus-worker.service
[Unit]
Description=Victus capture worker (WhatsApp + kiosk)
After=network-online.target

[Service]
# The wrapper resolves the app dir, loads worker.env, and sets PYTHONPATH.
Environment=PYTHON=/opt/victus/.venv/bin/python
Environment=WORKER_ENV_FILE=/opt/victus/worker.env
ExecStart=/opt/victus/apps/api/scripts/run-worker.sh --loop
Restart=always
RestartSec=5
User=victus

[Install]
WantedBy=multi-user.target
```

```bash
# one-time
python3.12 -m venv /opt/victus/.venv && . /opt/victus/.venv/bin/activate
pip install -r /opt/victus/apps/api/requirements-cpanel.txt
# WhatsApp video rail only:  pip install opencv-python-headless
cp /opt/victus/apps/api/worker.env.example /opt/victus/worker.env   # then edit
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

**Kiosk rail** (works even while WhatsApp is off):

1. Complete a capture at a kiosk terminal → a `processing_jobs` row appears with
   `channel=KIOSK`, `status=QUEUED`.
2. Within a minute (cron) / seconds (loop) the row moves to `SUCCEEDED` and the
   run logs `kiosk_result_sent` (or `worker_run_once_complete kiosk=1`).
3. A `toi_assessments` row is written for the participant, visible in the
   clinician app, with a `PATHWAY_B_ASSESSMENT_COMPLETED` audit entry.
4. **Delivery caveat:** the participant's portal link + one-time code go over
   WhatsApp, so they only actually arrive once `WHATSAPP_SEND_ENABLED=true`. While
   it is off, the capture is still processed and clinician-visible; the delivery
   message is written to the worker log instead of being sent (`whatsapp_rail_disabled`).

**WhatsApp rail** (needs Meta verification + `WHATSAPP_SEND_ENABLED=true`):

1. Send a real WhatsApp check-up through to the video step (a `processing_jobs`
   row appears with `channel=WHATSAPP`, `status=QUEUED`).
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
- **No reply sent / `whatsapp_rail_disabled` in the log** — `WHATSAPP_SEND_ENABLED`
  is not `true`, so the worker is intentionally not calling Meta. Set it to `true`
  (with the token + phone id) once verification is done.
- **`whatsapp_rail_misconfigured`** — `WHATSAPP_SEND_ENABLED=true` but
  `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` is missing; set both. The
  vitals still persist, only the outbound message fails.
- **Worker won't boot in production** — a placeholder `JWT_SECRET_KEY` /
  `INTERNAL_SERVICE_TOKEN` / `PSEUDO_SALT`; set the real values (same as the API).
