#!/usr/bin/env bash
# dev.sh — start backend and frontend development servers
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; RED='\033[0;31m'; RESET='\033[0m'
info() { echo -e "${GREEN}[dev]${RESET} $*"; }
die()  { echo -e "${RED}[dev]${RESET} $*" >&2; exit 1; }

[ -f "$PROJECT_DIR/.env" ]        || die "No .env found — run ./install.sh first"
command -v uvicorn &>/dev/null     || die "uvicorn not found — run ./install.sh first"
command -v npm &>/dev/null         || die "npm not found — install Node.js 20+"

cleanup() {
  info "Stopping servers..."
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

info "Starting backend  → http://localhost:8000"
cd "$PROJECT_DIR"
uvicorn syndication.main:app --reload --port 8000 &
BACKEND_PID=$!

info "Starting frontend → http://localhost:4200"
cd "$PROJECT_DIR/frontend"
npm start
