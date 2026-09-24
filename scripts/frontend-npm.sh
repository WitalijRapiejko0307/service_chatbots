#!/usr/bin/env bash
# Run npm commands against frontend/ using the exact Node/npm version that
# docker/Dockerfile.frontend (and therefore Railway) builds with, so
# package-lock.json can never drift out of sync with the image that actually
# runs `npm ci` in production.
#
# Background: frontend/package-lock.json was once regenerated with npm 12
# (Node 24, a typical dev host) while the Docker build uses node:20-alpine
# (npm 10.x). `npm ci` refused to run inside the image, causing every Railway
# deploy to fail instantly with no useful build log. See
# docs/fix/frontend-lockfile-docker-sync.md for the full incident writeup.
#
# Usage (from repo root or anywhere):
#   ./scripts/frontend-npm.sh install some-package
#   ./scripts/frontend-npm.sh install
#   ./scripts/frontend-npm.sh update
#   ./scripts/frontend-npm.sh ci
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"
NODE_IMAGE="node:20-alpine"

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <npm-args...>" >&2
  echo "Example: $0 install next-themes" >&2
  exit 1
fi

exec docker run --rm \
  -v "$FRONTEND_DIR":/app \
  -w /app \
  "$NODE_IMAGE" \
  sh -c "apk add --no-cache libc6-compat >/dev/null 2>&1; npm $*"
