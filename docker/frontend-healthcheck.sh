#!/bin/sh
set -eu
if [ -n "${BACKEND_INTERNAL_URL:-}" ]; then
  curl -fsS "http://127.0.0.1:${PORT:-8080}/admin/login" >/dev/null
else
  curl -fsS "http://127.0.0.1:${PORT:-3000}/admin/login" >/dev/null
fi
