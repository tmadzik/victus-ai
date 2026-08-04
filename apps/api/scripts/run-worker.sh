#!/usr/bin/env bash
# Run the Victus capture worker (WhatsApp + kiosk queues) — one process, both
# channels. Used by cPanel cron (`--once`) and systemd (`--loop`); see
# WORKER_DEPLOYMENT.md. Keeps cron/systemd lines short and hard to misconfigure:
# it resolves the app dir, loads the env file, sets PYTHONPATH, and execs.
#
#   cron:    * * * * * /home/USER/victus/apps/api/scripts/run-worker.sh --once >> ~/victus-worker.log 2>&1
#   systemd: ExecStart=/opt/victus/apps/api/scripts/run-worker.sh --loop
#   local:   PYTHON=.venv/bin/python ./scripts/run-worker.sh --once --local-media
#
# Env:
#   WORKER_ENV_FILE  path to the env file to source (default: <api>/worker.env)
#   PYTHON           interpreter to use (default: python3); point at the venv's
#                    python on cPanel, e.g. ~/virtualenv/victus-api/3.12/bin/python
set -euo pipefail

# apps/api/ is the parent of this script's dir, regardless of where cron cd's to.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(dirname -- "$SCRIPT_DIR")"

ENV_FILE="${WORKER_ENV_FILE:-$API_DIR/worker.env}"
if [[ -f "$ENV_FILE" ]]; then
  # Export every assignment in the env file (it uses `KEY=value`, not `export`).
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

# The worker imports the package from source; prepend so it always wins.
export PYTHONPATH="$API_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHON="${PYTHON:-python3}"
exec "$PYTHON" -m victus_api.worker "$@"
