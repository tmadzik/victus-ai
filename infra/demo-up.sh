#!/usr/bin/env bash
# Bring the whole Victus platform up on localhost for an internal review / demo.
#
#   ./infra/demo-up.sh            # start (and seed on first run)
#   ./infra/demo-up.sh --reseed   # start and re-run the demo-data seeder
#
# Isolated by design: its own Docker volumes, its own database. It does not
# touch ~/.victus-local or any other environment.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="infra/.env.local"
COMPOSE=(docker compose -f infra/docker-compose.prod.yml -f infra/docker-compose.local.yml --env-file "$ENV_FILE")

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

if ! docker info >/dev/null 2>&1; then
  echo "Docker isn't running. Start Docker Desktop / OrbStack and try again." >&2
  exit 1
fi

# --- 1. config (generated once, then reused so data + logins persist) --------
if [ ! -f "$ENV_FILE" ]; then
  say "First run — generating $ENV_FILE with fresh local secrets"
  cat > "$ENV_FILE" <<EOF
# Local demo configuration — generated $(date -u +%FT%TZ). Not for production.
ROOT_DOMAIN=localhost
WWW_DOMAIN=localhost
APP_DOMAIN=localhost
API_DOMAIN=localhost
PUBLIC_WWW_URL=http://localhost:3001
PUBLIC_APP_URL=http://localhost:3000
PUBLIC_API_URL=http://localhost:8000
ACME_EMAIL=demo@localhost

POSTGRES_USER=victus
POSTGRES_DB=victus
POSTGRES_PASSWORD=$(openssl rand -hex 24)

JWT_SECRET_KEY=$(openssl rand -hex 32)
INTERNAL_SERVICE_TOKEN=$(openssl rand -hex 32)
PSEUDO_SALT=$(openssl rand -hex 32)
KIOSK_ENCRYPTION_KEY=$(openssl rand -hex 32)
AUTH_SECRET=$(openssl rand -base64 48)

SITE_CODE=DEMO
EOF
fi

# --- 2. build + start --------------------------------------------------------
say "Building and starting the stack (first build takes a few minutes)"
"${COMPOSE[@]}" up -d --build

# --- 3. wait for the API to be ready ----------------------------------------
say "Waiting for the API (migrations run automatically on boot)"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/readyz >/dev/null 2>&1; then
    echo "  API ready."
    break
  fi
  [ "$i" = "60" ] && { echo "  API did not become ready — check: ${COMPOSE[*]} logs api" >&2; exit 1; }
  sleep 2
done

# --- 4. seed demo data -------------------------------------------------------
# Always run it: the seeder is idempotent (existing accounts and histories are
# skipped), and keying off the config file instead would miss the case where the
# database was wiped but infra/.env.local survived.
say "Seeding the demo cohort"
API_URL=http://localhost:8000 python3 infra/seed-demo-data.py

say "Victus is running locally"
cat <<'EOF'

  Marketing site   http://localhost:3001
  Clinical app     http://localhost:3000
  API docs         http://localhost:8000/docs

  Sign in with the demo accounts printed above.
  Walkthrough for the session:  DEMO.md

  Stop it with:  ./infra/demo-down.sh
EOF
