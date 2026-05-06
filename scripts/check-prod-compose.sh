#!/usr/bin/env bash
# Guard that docker-compose.yml (the production invocation base file) never
# publishes the database (5432) or raw API (8000) ports to the host. Both dev
# bindings live in docker-compose.override.yml, which is NOT loaded when
# CI/prod runs `docker compose -f docker-compose.yml up`.
#
# Wire this into CI alongside the other lint/test steps:
#   scripts/check-prod-compose.sh

set -euo pipefail

COMPOSE_FILE="${1:-docker-compose.yml}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "check-prod-compose: $COMPOSE_FILE not found" >&2
  exit 2
fi

# Extract the db service block and fail if it declares a `ports:` mapping.
# yq would be cleaner, but awk keeps this dependency-free.
offending=$(awk '
  /^services:/         { in_services=1; next }
  in_services && /^[a-zA-Z]/ { in_services=0 }
  in_services && /^  db:/    { in_db=1; next }
  in_db && /^  [a-zA-Z]/     { in_db=0 }
  in_db && /^    ports:/     { print NR": "$0; found=1 }
  END { exit !found }
' "$COMPOSE_FILE" || true)

if [[ -n "$offending" ]]; then
  echo "check-prod-compose: db service publishes ports in $COMPOSE_FILE" >&2
  echo "$offending" >&2
  echo "Move the binding to docker-compose.override.yml (dev only)." >&2
  exit 1
fi

# Also sanity-check: 5432 must not appear as a host-side port anywhere in the
# prod compose file. Catches both db and any future service that might tunnel it.
if grep -Eq '^\s*-\s*"?[0-9.:]*5432:' "$COMPOSE_FILE"; then
  echo "check-prod-compose: 5432 host binding found in $COMPOSE_FILE" >&2
  grep -nE '^\s*-\s*"?[0-9.:]*5432:' "$COMPOSE_FILE" >&2
  exit 1
fi

# I-01: 8000 must not be published on the host either. Exposing the raw FastAPI
# backend bypasses nginx's rate-limit zone, CSP injection, and XFF normalization.
if grep -Eq '^\s*-\s*"?[0-9.:]*8000:' "$COMPOSE_FILE"; then
  echo "check-prod-compose: 8000 host binding found in $COMPOSE_FILE" >&2
  grep -nE '^\s*-\s*"?[0-9.:]*8000:' "$COMPOSE_FILE" >&2
  echo "Move the binding to docker-compose.override.yml (dev only)." >&2
  exit 1
fi

echo "check-prod-compose: OK — $COMPOSE_FILE does not expose 5432 or 8000."
