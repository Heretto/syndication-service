# Syndication Service — agent notes

Built on [hop-core](https://github.com/Heretto/hop-core), pinned at v0.1.3.

## Before changing anything

```bash
python3 -c "from hop_core.doctor import main; import sys; sys.exit(main())"
```

hop-doctor audits the hop-core integration and exits non-zero on real problems.
Run it after any change to dependencies, Docker config, or the Angular build.

## hop-core references — a different repository, not loaded here

- Integration rules, failure modes, upgrade steps: hop-core `AGENTS.md`
- Design system, components, tokens, app skeleton: hop-core `DESIGN-SYSTEM.md`

Read those instead of inferring from this project's code. Do not copy them here.

## What is specific to this project

**Settings:** `.env` at the project root (gitignored). Copy `.env.example` and
generate the three required secrets before starting:

```bash
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python3 -c "import secrets; print('APP_SECRET_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"
```

`ENCRYPTION_KEY` cannot be rotated after first run — changing it makes existing
encrypted credentials unreadable.

**Start the stack (local dev):**

```bash
# Terminal 1 — backend (port 8000)
pip install -r requirements.txt && pip install -e ".[dev]"
alembic upgrade head
uvicorn syndication.main:app --reload --port 8000

# Terminal 2 — frontend (port 4200, proxies /api → :8000)
cd frontend && npm install && npm start
```

**First admin account:**

```bash
python3 scripts/seed.py   # prompts for email + password
```

Or set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` — the backend creates the
account automatically on startup.

**Non-obvious things:**

- Both the backend and frontend Docker builds are fully self-contained. The
  frontend installs `@heretto/hop-ui` from the npm tarball declared in
  `package.json`; no `hop-core/` sibling directory is required for Docker.
- SQLite is the default (`DATABASE_URL=sqlite:///./syndication.db`). Use
  PostgreSQL in production (`DATABASE_URL=postgresql+psycopg2://...`).
- Collection API routes require a trailing slash: `/api/v1/syncs/` not
  `/api/v1/syncs`. Without it you get 404, not a routing error.
- Every API route requires a valid JWT. `401` from an unauthenticated request is
  correct behaviour; the app has no public health endpoint.

## Upgrading hop-core

Resolve the current release (hop-core `AGENTS.md`, Step 0), then:

1. Bump `requirements.txt` and `pyproject.toml` to the new Python tag.
2. Bump `frontend/package.json` `@heretto/hop-ui` to the new release asset URL.
3. Regenerate the npm lock: `cd frontend && npm install`.
4. Re-run hop-doctor and the test suite.
