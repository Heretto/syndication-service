#!/usr/bin/env bash
# Start the syndication service with Docker Compose.
# Handles first-run setup: copies .env.example, generates missing secrets,
# and reminds you to create an admin account if ADMIN_EMAIL is not set.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

# ── Copy .env.example if .env is missing ──────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  echo "Created .env from .env.example."
  echo "Review it and set ADMIN_EMAIL / ADMIN_PASSWORD before continuing."
  echo ""
fi

# ── Auto-fill any missing secrets ─────────────────────────────────────────────
_fill_random() {
  local key="$1"
  local current
  current=$(grep -E "^${key}=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | xargs || true)
  if [ -z "$current" ]; then
    local val
    val=$(python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")
    sed -i.bak "s|^${key}=.*|${key}=${val}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    echo "Generated ${key}."
  fi
}

_fill_random APP_SECRET_KEY
_fill_random JWT_SECRET_KEY

enc=$(grep -E "^ENCRYPTION_KEY=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | xargs || true)
if [ -z "$enc" ]; then
  val=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  sed -i.bak "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${val}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
  echo "Generated ENCRYPTION_KEY."
fi

# ── Warn if no admin email is configured ──────────────────────────────────────
admin_email=$(grep -E "^ADMIN_EMAIL=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | xargs || true)
if [ -z "$admin_email" ]; then
  echo ""
  printf '\033[33mWarning: ADMIN_EMAIL is not set.\033[0m\n'
  echo "After startup, create the first admin account with:"
  echo "  docker compose exec backend python scripts/seed.py"
  echo ""
fi

# ── Launch ────────────────────────────────────────────────────────────────────
cd "$ROOT"
exec docker compose up --build "$@"
