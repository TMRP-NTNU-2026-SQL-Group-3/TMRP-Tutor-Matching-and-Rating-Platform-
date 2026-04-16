#!/bin/sh
set -e
# SEC-H04: construct DATABASE_URL from Docker secret instead of plain env var.
# Falls back to DATABASE_URL if the secret file is absent (local dev).
if [ -f /run/secrets/db_password ]; then
  DB_PASS=$(cat /run/secrets/db_password)
  export DATABASE_URL="postgresql://${DB_USER:?}:${DB_PASS}@${DB_HOST:-db}:5432/${DB_NAME:?}"
fi

exec "$@"
