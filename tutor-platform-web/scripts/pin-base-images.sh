#!/usr/bin/env bash
# Resolve the two base-image tags used by ../Dockerfile to immutable @sha256
# digests and rewrite the Dockerfile in place. The floating tags
# (node:20-alpine, nginxinc/nginx-unprivileged:alpine) otherwise re-resolve
# on every `docker build`, which means a compromised registry publish or an
# unvetted upstream change silently lands in production.
#
# Usage:  ./scripts/pin-base-images.sh [--check]
#   --check   exit 1 if the Dockerfile still contains unpinned FROM tags
#             (for CI). Without the flag, the script rewrites in place.
#
# Requires: docker (to pull + inspect the manifest). Run this before tagging
# a release; commit the resulting Dockerfile diff so the build is frozen.

set -euo pipefail

readonly DOCKERFILE="$(cd "$(dirname "$0")/.." && pwd)/Dockerfile"
readonly IMAGES=(
  "node:20-alpine"
  "nginxinc/nginx-unprivileged:alpine"
)

check_only=0
if [[ "${1:-}" == "--check" ]]; then
  check_only=1
fi

if [[ $check_only -eq 1 ]]; then
  # Any bare FROM without @sha256 is a failure. The regex tolerates AS clauses
  # and leading whitespace but rejects floating tags like :alpine.
  if grep -E '^\s*FROM\s+[^@]+$' "$DOCKERFILE" >/dev/null; then
    echo "ERR: Dockerfile contains unpinned FROM lines:" >&2
    grep -nE '^\s*FROM\s+[^@]+$' "$DOCKERFILE" >&2
    exit 1
  fi
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERR: docker is required to resolve image digests" >&2
  exit 1
fi

for image in "${IMAGES[@]}"; do
  echo "Resolving $image ..."
  docker pull --quiet "$image" >/dev/null
  digest="$(docker inspect --format='{{index .RepoDigests 0}}' "$image" | awk -F'@' '{print $2}')"
  if [[ -z "$digest" ]]; then
    echo "ERR: could not resolve digest for $image" >&2
    exit 1
  fi
  # Replace the exact tag with tag@sha256:... — preserves AS <stage> suffixes
  # because we anchor on the image reference rather than the whole line.
  # Use `|` as the sed delimiter because image refs contain `/` (e.g.
  # `nginxinc/nginx-unprivileged`), which would otherwise terminate the s///.
  # Escape the `|` defensively in case it ever appears in an image ref.
  pattern="${image//|/\\|}"
  replacement="${image//|/\\|}@${digest}"
  sed -i.bak -E "s|^(FROM[[:space:]]+)${pattern}([[:space:]]|$)|\1${replacement}\2|" "$DOCKERFILE"
  rm -f "${DOCKERFILE}.bak"
  echo "  -> ${image}@${digest}"
done

echo "Done. Review the Dockerfile diff and commit."
