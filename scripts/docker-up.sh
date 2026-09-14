#!/usr/bin/env bash
# docker-up.sh — bring up the Docker stack, generating any missing secrets first.
# Run from anywhere: bash scripts/docker-up.sh [extra docker compose args]
#
# Existing values in .env are never overwritten. This matters most for
# ENCRYPTION_KEY: stored credentials are encrypted with a key derived from it,
# so regenerating it would orphan every encrypted row.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.example"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()    { echo -e "${GREEN}[docker-up]${RESET} $*"; }
warning() { echo -e "${YELLOW}[docker-up]${RESET} $*"; }
die()     { echo -e "${RED}[docker-up]${RESET} $*" >&2; exit 1; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
command -v docker &>/dev/null || die "docker not found — see https://docs.docker.com/get-docker/"
docker compose version &>/dev/null || die "docker compose v2 not available"
docker info &>/dev/null || die "the Docker daemon is not running — start Docker and retry"

# ── Secret generation ─────────────────────────────────────────────────────────
generate_secret() {
  if command -v openssl &>/dev/null; then
    openssl rand -hex 32
  elif command -v python3 &>/dev/null; then
    python3 -c "import secrets; print(secrets.token_hex(32))"
  else
    die "need either openssl or python3 to generate secrets"
  fi
}

generate_fernet_key() {
  if command -v python3 &>/dev/null; then
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  else
    die "python3 is required to generate ENCRYPTION_KEY"
  fi
}

# Sets $key in .env only when it has no value. Returns 0 if it generated one.
ensure_key() {
  local key="$1" generator="${2:-generate_secret}" value
  if grep -qE "^${key}=.+" "$ENV_FILE"; then
    return 1
  fi
  value="$($generator)"
  if grep -qE "^${key}=[[:space:]]*$" "$ENV_FILE"; then
    awk -v k="$key" -v v="$value" '
      $0 ~ "^"k"=[[:space:]]*$" { print k"="v; next }
      { print }
    ' "$ENV_FILE" > "$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
  return 0
}

# ── Ensure .env exists ────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  [ -f "$ENV_EXAMPLE" ] || die ".env.example not found — is this the project root?"
  info "No .env found — creating one from .env.example"
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# ── Fill in required secrets ──────────────────────────────────────────────────
GENERATED=()
for key in APP_SECRET_KEY JWT_SECRET_KEY; do
  if ensure_key "$key" generate_secret; then
    GENERATED+=("$key")
  fi
done
if ensure_key "ENCRYPTION_KEY" generate_fernet_key; then
  GENERATED+=("ENCRYPTION_KEY")
fi

if [ ${#GENERATED[@]} -gt 0 ]; then
  info "Generated ${#GENERATED[@]} secret(s) in .env: ${GENERATED[*]}"
  for key in "${GENERATED[@]}"; do
    if [ "$key" = "ENCRYPTION_KEY" ]; then
      echo ""
      warning "ENCRYPTION_KEY was just generated. Back it up somewhere recoverable."
      warning "It encrypts stored credentials; losing or changing it makes"
      warning "existing encrypted rows unreadable."
      echo ""
    fi
  done
else
  info "All required secrets already present in .env — leaving them untouched"
fi

# ── Warn about missing first-run admin ────────────────────────────────────────
if ! grep -qE "^ADMIN_EMAIL=.+" "$ENV_FILE"; then
  echo ""
  warning "ADMIN_EMAIL is not set in .env."
  warning "The app will start, but you will not be able to log in."
  warning "Set ADMIN_EMAIL and ADMIN_PASSWORD in .env before running, or"
  warning "create an account manually after startup:"
  warning "  docker compose exec backend python scripts/seed.py"
  echo ""
fi

# ── Bring up the stack ────────────────────────────────────────────────────────
info "Starting containers..."
cd "$PROJECT_DIR"
docker compose up -d "$@"

echo ""
info "Stack is up"
echo "  Frontend  → http://localhost:4200"
echo "  API       → http://localhost:8000"
echo "  API docs  → http://localhost:8000/docs"
echo ""
echo "  Logs:  docker compose logs -f backend"
echo "  Stop:  docker compose down"
echo ""
