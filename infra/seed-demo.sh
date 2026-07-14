#!/usr/bin/env bash
# Seed two demo accounts so a founder/investor can click through the whole
# platform immediately. Idempotent-ish: re-registering an existing email just
# logs a notice and the script carries on to (re)grant consents.
#
#   API_URL=https://api.victusdata.com ./infra/seed-demo.sh
#   (defaults to https://api.victusdata.com)
#
# Prints the demo credentials at the end. These are DEMO accounts — do not use
# real patient data.
set -euo pipefail

API_URL="${API_URL:-https://api.victusdata.com}"
PASSWORD="${DEMO_PASSWORD:-VictusDemo!2026}"

CLINICIAN_EMAIL="clinician@demo.victusdata.com"
PATIENT_EMAIL="patient@demo.victusdata.com"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# Extract "access_token":"..." from a JSON blob without needing jq/python.
extract_token() {
  grep -oE '"access_token":"[^"]+"' | head -1 | sed -E 's/.*:"([^"]+)"/\1/'
}

register() {
  # $1 email  $2 role  $3 full name
  curl -fsS -X POST "$API_URL/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\",\"full_name\":\"$3\",\"role\":\"$2\"}" \
    2>/dev/null || return 1
}

login() {
  # $1 email  -> prints access token
  curl -fsS -X POST "$API_URL/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}" | extract_token
}

grant_consents() {
  # $1 bearer token
  curl -fsS -X PATCH "$API_URL/users/me/consents" \
    -H "Authorization: Bearer $1" \
    -H 'Content-Type: application/json' \
    -d '{"grants":["TRIAGE","TOI_IMAGING"],"revokes":[]}' >/dev/null
}

say "Seeding demo accounts against $API_URL"

if register "$CLINICIAN_EMAIL" "CLINICIAN" "Demo Clinician" >/dev/null; then
  echo "  ✓ created clinician $CLINICIAN_EMAIL"
else
  echo "  • clinician already exists (or registration closed) — continuing"
fi

if register "$PATIENT_EMAIL" "PATIENT" "Demo Patient" >/dev/null; then
  echo "  ✓ created patient $PATIENT_EMAIL"
else
  echo "  • patient already exists — continuing"
fi

echo "  … granting the patient's triage + TOI imaging consents"
PATIENT_TOKEN="$(login "$PATIENT_EMAIL")"
if [ -n "${PATIENT_TOKEN:-}" ]; then
  grant_consents "$PATIENT_TOKEN"
  echo "  ✓ consents granted"
else
  echo "  ! could not log the patient in to grant consents — check the API is up"
fi

say "Demo accounts ready — sign in at ${PUBLIC_APP_URL:-https://app.victusdata.com}"
cat <<EOF

  Clinician : $CLINICIAN_EMAIL
  Patient   : $PATIENT_EMAIL
  Password  : $PASSWORD

  Clinician sees the participant search, /research console, trajectories and
  the rising-risk nudges. Patient can run a Pathway A triage and an in-browser
  TOI/rPPG capture. (These are demo logins — no real patient data.)
EOF
