#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=compose-common.sh
source "$ROOT/scripts/compose-common.sh"

copy_if_missing() {
  local src="$1"
  local dest="$2"
  if [ ! -f "$dest" ]; then
    cp "$src" "$dest"
    echo "Created $dest from $src"
  else
    echo "Already exists: $dest (skipped)"
  fi
}

echo "==> Setting up local Docker environment"
compose_warn_legacy

copy_if_missing ".env.docker.example" ".env"
copy_if_missing "backend/.env.example" "backend/.env"
copy_if_missing "frontend/.env.local.example" "frontend/.env.local"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if ! grep -q '^SECRET_ENCRYPTION_KEY=.\+' backend/.env 2>/dev/null; then
  echo ""
  echo "Generating SECRET_ENCRYPTION_KEY in backend/.env..."
  KEY=""
  if command -v python3 >/dev/null 2>&1; then
    KEY="$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)"
  fi
  if [ -z "${KEY:-}" ]; then
    echo "Host lacks cryptography — generating via backend container..."
    compose_run build backend >/dev/null
    KEY="$(compose_run run --rm --no-deps backend python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
  fi
  if grep -q '^SECRET_ENCRYPTION_KEY=' backend/.env; then
    sed -i "s|^SECRET_ENCRYPTION_KEY=.*|SECRET_ENCRYPTION_KEY=${KEY}|" backend/.env
  else
    echo "SECRET_ENCRYPTION_KEY=${KEY}" >> backend/.env
  fi
  echo "SECRET_ENCRYPTION_KEY generated."
fi

echo ""
echo "==> Starting Postgres and Redis"
compose_run up -d postgres redis

echo "==> Waiting for Postgres to be healthy"
for i in $(seq 1 30); do
  if compose_run exec -T postgres pg_isready -U "${POSTGRES_USER:-agent}" -d "${POSTGRES_DB:-service_chatbot}" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Postgres did not become healthy in time"
    exit 1
  fi
  sleep 2
done

echo "==> Running database migrations"
compose_run --profile setup run --rm migrate

echo ""
echo "Setup complete."
echo "  Bootstrap admin: admin@example.com / changeme123"
echo "  1. Optional: set OPENAI_API_KEY in backend/.env for live agent replies"
echo "  2. Run: ./scripts/dev-up.sh"
echo "  3. Admin login: http://localhost:3000/admin/login"
echo "  4. API health:  http://localhost:8000/health"
