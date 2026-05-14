#!/bin/sh
set -e

# C-1: refuse to start in DEBUG mode unless ALLOW_DEBUG=true is set explicitly.
# DEBUG=true exposes /docs, /redoc, /openapi.json and disables the Secure flag
# on auth cookies. Requiring ALLOW_DEBUG=true as a paired consent flag ensures
# a developer cannot accidentally include docker-compose.run.yml in a
# public-facing stack without acknowledging the risks. The run file sets both
# DEBUG=true and ALLOW_DEBUG=true together.
if [ "${DEBUG:-false}" = "true" ]; then
  if [ "${ALLOW_DEBUG:-false}" != "true" ]; then
    echo "FATAL: DEBUG=true requires ALLOW_DEBUG=true to be set explicitly." >&2
    echo "  This mode exposes /docs, /redoc, /openapi.json and disables the" >&2
    echo "  Secure flag on auth cookies. Development environments only." >&2
    echo "  Set ALLOW_DEBUG=true to confirm you accept these risks." >&2
    exit 1
  fi
  echo "WARNING: DEBUG mode active — schema endpoints exposed; COOKIE_SECURE may be false. Development use only." >&2
fi

# SEC-H04 / CRITICAL-1: load secrets from Docker secret files rather than env
# vars committed in .env.docker. Each block is independent: if a secret file is
# absent (e.g. local dev without compose), fall back to whatever is already in
# the env so uvicorn / tests still work.

# Strip trailing CR/LF from a secret file — Windows editors often save as CRLF,
# which Postgres's POSTGRES_PASSWORD_FILE reader tolerates but `cat` does not.
# tr -d drops both so DATABASE_URL/JWT values don't carry stray whitespace.
read_secret() {
  tr -d '\r\n' < "$1"
}

if [ -f /run/secrets/db_password ]; then
  DB_PASS=$(read_secret /run/secrets/db_password)
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
  JWT_SECRET_KEY=$(read_secret /run/secrets/jwt_secret_key)
  # HIGH-4: mirror the db_password guard — refuse to boot on empty or
  # placeholder JWT signing keys. config.py also rejects some placeholder
  # strings, but it only runs after env export; an empty file here would
  # trigger a far less actionable "JWT_SECRET_KEY must be >= 32 chars"
  # pydantic error at import time.
  case "$JWT_SECRET_KEY" in
    ""|"REPLACE_ME"|"REPLACE_WITH_HEX_FROM_secrets.token_hex_32_AT_LEAST_32_CHARS"|"change-me-in-production"|"change-me")
      echo "FATAL: /run/secrets/jwt_secret_key is empty or a known placeholder." >&2
      echo "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'" >&2
      exit 1
      ;;
  esac
  export JWT_SECRET_KEY
fi

# Optional — present only during a rotation window. An empty file is a
# legitimate "no rotation in flight" signal, so don't treat empty as fatal
# here; just skip the export. A non-empty-but-placeholder value is still
# rejected so a rotation can't silently fall back to a known secret.
if [ -f /run/secrets/jwt_secret_key_previous ]; then
  JWT_SECRET_KEY_PREVIOUS=$(read_secret /run/secrets/jwt_secret_key_previous)
  case "$JWT_SECRET_KEY_PREVIOUS" in
    "")
      ;;
    "REPLACE_ME"|"REPLACE_WITH_HEX_FROM_secrets.token_hex_32_AT_LEAST_32_CHARS"|"change-me-in-production"|"change-me")
      echo "FATAL: /run/secrets/jwt_secret_key_previous contains a placeholder value." >&2
      exit 1
      ;;
    *)
      export JWT_SECRET_KEY_PREVIOUS
      ;;
  esac
fi

if [ -f /run/secrets/admin_password ]; then
  ADMIN_PASSWORD=$(read_secret /run/secrets/admin_password)
  case "$ADMIN_PASSWORD" in
    ""|"REPLACE_ME"|"REPLACE_WITH_STRONG_PASSWORD_12PLUS_MIXED"|"REPLACE_WITH_STRONG_PASSWORD_16PLUS_ALL4CLASSES"|"REPLACE_WITH_A_STRONG_PASSWORD_MIN_8_CHARS"|"REPLACE_WITH_A_STRONG_PASSWORD_16PLUS_ALL_4_CLASSES"|"admin"|"admin123"|"password"|"changeme")
      echo "FATAL: /run/secrets/admin_password is empty or a known placeholder." >&2
      echo "Edit ./secrets/admin_password.txt with a strong password (16+ chars, all 4 classes: lower/upper/digit/symbol)." >&2
      exit 1
      ;;
  esac
  export ADMIN_PASSWORD
fi

# Pre-create the huey SQLite task queue with restricted permissions so the
# OS umask cannot produce a world-readable file containing task payloads.
# SQLite honours pre-existing file permissions when opening an existing file.
mkdir -p data
touch data/huey.db
chmod 600 data/huey.db

exec "$@"
