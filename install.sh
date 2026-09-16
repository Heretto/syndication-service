#!/usr/bin/env bash
# install.sh — first-time local development setup
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.example"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()    { echo -e "${GREEN}[install]${RESET} $*"; }
warning() { echo -e "${YELLOW}[install]${RESET} $*"; }
die()     { echo -e "${RED}[install]${RESET} $*" >&2; exit 1; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
command -v python3 &>/dev/null || die "python3 not found — install Python 3.11+"
command -v node &>/dev/null    || die "node not found — install Node.js 20+"
command -v npm &>/dev/null     || die "npm not found — install Node.js 20+"

# ── .env ──────────────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  [ -f "$ENV_EXAMPLE" ] || die ".env.example not found — is this the project root?"
  info "Creating .env from .env.example..."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# ── Secret generation ─────────────────────────────────────────────────────────
generate_secret() {
  if command -v openssl &>/dev/null; then openssl rand -hex 32
  else python3 -c "import secrets; print(secrets.token_hex(32))"; fi
}
generate_fernet_key() {
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}
ensure_key() {
  local key="$1" generator="${2:-generate_secret}" value
  grep -qE "^${key}=.+" "$ENV_FILE" && return 1
  value="$($generator)"
  if grep -qE "^${key}=[[:space:]]*$" "$ENV_FILE"; then
    awk -v k="$key" -v v="$value" \
      '$0 ~ "^"k"=[[:space:]]*$" { print k"="v; next } { print }' \
      "$ENV_FILE" > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
  return 0
}

GENERATED=()
for key in APP_SECRET_KEY JWT_SECRET_KEY; do
  ensure_key "$key" generate_secret && GENERATED+=("$key") || true
done
ensure_key "ENCRYPTION_KEY" generate_fernet_key && GENERATED+=("ENCRYPTION_KEY") || true

if [ ${#GENERATED[@]} -gt 0 ]; then
  info "Generated secrets: ${GENERATED[*]}"
  if printf '%s\n' "${GENERATED[@]}" | grep -q ENCRYPTION_KEY; then
    echo ""
    warning "ENCRYPTION_KEY was just generated — back it up."
    warning "Changing it later makes existing encrypted credentials unreadable."
    echo ""
  fi
fi

# ── Python dependencies ───────────────────────────────────────────────────────
info "Installing Python dependencies..."
cd "$PROJECT_DIR"
pip install -r requirements.txt
pip install -e ".[dev]"

# ── Database migrations ───────────────────────────────────────────────────────
info "Running database migrations..."
alembic upgrade head

# ── Frontend dependencies ─────────────────────────────────────────────────────
info "Installing frontend dependencies..."
cd "$PROJECT_DIR/frontend"
npm install
cd "$PROJECT_DIR"

# ── Admin account ─────────────────────────────────────────────────────────────
info "Creating admin account..."
python3 scripts/seed.py

echo ""
info "Installation complete. Run ./dev.sh to start the development servers."
echo ""
