#!/usr/bin/env sh
# Apply DB migrations (API container only) then hand off to the given command.
# Idempotent: `alembic upgrade head` is a no-op once the DB is at head, so it is
# safe on every restart. The retry loop absorbs the window while Postgres is
# still starting.
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] applying database migrations..."
  n=0
  until alembic upgrade head; do
    n=$((n + 1))
    if [ "$n" -ge 30 ]; then
      echo "[entrypoint] database not reachable after 30 attempts — giving up" >&2
      exit 1
    fi
    echo "[entrypoint]   database not ready yet (attempt $n) — retrying in 2s"
    sleep 2
  done
  echo "[entrypoint] migrations applied."
fi

exec "$@"
