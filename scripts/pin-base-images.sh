#!/usr/bin/env bash
# MEDIUM-10: resolve current base-image tags to immutable @sha256 digests and
# rewrite the Dockerfiles / docker-compose.yml in place.
#
# Run locally (needs a working Docker daemon + outbound registry access) any
# time the base images are bumped. Until Renovate is wired up, this is the
# authoritative way to refresh the pins.
#
# Usage: ./scripts/pin-base-images.sh [--dry-run]

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY_RUN=1; fi

# Image references we want pinned. Keep the tag here — the digest is what
# gets appended after `@` in the Dockerfile / compose file.
IMAGES=(
  "python:3.12-slim"
  "node:20-alpine"
  "nginxinc/nginx-unprivileged:alpine"
  "postgres:16-alpine"
)

resolve_digest() {
  local ref="$1"
  # `docker buildx imagetools inspect` works for multi-arch manifests too.
  docker buildx imagetools inspect "$ref" --format '{{json .Manifest}}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["digest"])'
}

for ref in "${IMAGES[@]}"; do
  digest="$(resolve_digest "$ref")"
  echo "$ref  ->  $ref@$digest"
  if [[ $DRY_RUN -eq 1 ]]; then continue; fi

  # Replace `image:tag` occurrences, but only when not already pinned
  # (grep -v '@sha256:' avoids double-pinning).
  escaped_ref="$(printf '%s' "$ref" | sed 's/[\/&]/\\&/g')"
  escaped_new="$(printf '%s' "$ref@$digest" | sed 's/[\/&]/\\&/g')"
  grep -rl --include='Dockerfile*' --include='docker-compose*.yml' "$ref" . \
    | while read -r f; do
        # Skip lines that already carry a digest for this base.
        grep -q "${ref}@sha256:" "$f" && continue || true
        sed -i.bak "s|${escaped_ref}\$|${escaped_new}|g; s|${escaped_ref}\([^0-9A-Za-z@]\)|${escaped_new}\1|g" "$f" \
          || { echo "pin-base-images: sed failed on $f" >&2; rm -f "${f}.bak"; exit 1; }
        rm -f "${f}.bak"
      done
done

echo "Done. Commit the updated Dockerfile / docker-compose.yml files."
