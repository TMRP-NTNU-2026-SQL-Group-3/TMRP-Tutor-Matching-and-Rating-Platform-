#!/bin/sh
set -e
# SEC-H04 / CRITICAL-1: load secrets from Docker secret files rather than env
# vars committed in .env.docker. Each block is independent: if a secret file is
# absent (e.g. local dev without compose), fall back to whatever is already in
# the env so uvicorn / tests still work.

if [ -f /run/secrets/db_password ]; then
  DB_PASS=$(cat /run/secrets/db_password)
  # HIGH-4: refuse to boot with a known placeholder or empty secret. If
  # ./secrets/db_password.txt was copied from the shipped .example without
  # being edited, the Postgres password would otherwise be trivially guessable.
  case "$DB_PASS" in
    ""|"REPLACE_ME"|"please_change_me_to_a_strong_random_password"|"changeme"|"password"|"postgres")
      echo "FATAL: /run/secrets/db_password contains an empty or placeholder value." >&2
      echo "Edit ./secrets/db_password.txt with a strong random password before starting." >&2
      exit 1
      ;;
  esac
  export DATABASE_URL="postgresql://${DB_USER:?}:${DB_PASS}@${DB_HOST:-db}:5432/${DB_NAME:?}"
fi

if [ -f /run/secrets/jwt_secret_key ]; then
  JWT_SECRET_KEY=$(cat /run/secrets/jwt_secret_key)
  export JWT_SECRET_KEY
fi

# Optional — present only during a rotation window.
if [ -f /run/secrets/jwt_secret_key_previous ]; then
  JWT_SECRET_KEY_PREVIOUS=$(cat /run/secrets/jwt_secret_key_previous)
  export JWT_SECRET_KEY_PREVIOUS
fi

if [ -f /run/secrets/admin_password ]; then
  ADMIN_PASSWORD=$(cat /run/secrets/admin_password)
  export ADMIN_PASSWORD
fi

exec "$@"
