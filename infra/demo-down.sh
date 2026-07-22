#!/usr/bin/env bash
# Stop the localhost demo.
#
#   ./infra/demo-down.sh          # stop; database and logins are preserved
#   ./infra/demo-down.sh --wipe   # stop AND delete the demo database volume
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f infra/docker-compose.prod.yml -f infra/docker-compose.local.yml
         --env-file infra/.env.local --profile whatsapp)

if [ "${1:-}" = "--wipe" ]; then
  echo "Stopping and deleting the demo database volume..."
  "${COMPOSE[@]}" down -v
  echo "Wiped. The next ./infra/demo-up.sh will re-seed from scratch."
else
  "${COMPOSE[@]}" down
  echo "Stopped. Data is preserved — ./infra/demo-up.sh brings it straight back."
fi
