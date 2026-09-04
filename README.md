# Syndication Service

A pipeline that syncs DITA content from Heretto Deploy to Salesforce Knowledge on a schedule or on demand.

---

## Architecture

The service is built around three layers:

```
Heretto Deploy (source adapter)
        ↓
  IR Pipeline (runner)
        ↓
  Target Connector (salesforce | noop)
```

The pipeline works through a target-neutral **Intermediate Representation** (`IRPage`), so the source and target layers are fully decoupled. Adding a new connector does not require touching the source or pipeline code.

---

## Sync Pipeline

Each sync run executes the following stages:

| # | Stage | Description |
|---|-------|-------------|
| 1 | Extract | Fetch changed UUIDs from `/changed_content` (or full structure walk) |
| 2 | Fetch pages | Retrieve full content for each changed item |
| 3 | Sanitize HTML | Strip/transform HTML to the subset accepted by the target |
| 4 | Upload binaries | Download image assets from Deploy and upload to the target |
| 5 | Upsert articles | Create or update articles via the target API |
| 6 | Sync categories | Apply taxonomy → data category mappings (Salesforce only) |
| 7 | Publish | Make articles visible to end users |
| 8 | Archive removed | Unpublish articles that were deleted from Deploy |
| 9 | Deferred link fixup | Rewrite cross-article links after all articles are loaded |

### Incremental Sync

Uses the Deploy `/changed_content` endpoint with a **high-water-mark cursor**. Only articles with a `contentModificationDate` newer than the last successful run are fetched. The cursor advances after each successful run.

### Force Full Resync

Walks the complete `/structure` tree and fetches every topic regardless of modification date. Useful when articles exist in Deploy but were never emitted by the changeset endpoint (e.g. content published before sync tracking began). The high-water-mark cursor is **not** advanced after a forced resync.

> The pipeline is stateless. The executor layer is responsible for persisting the cursor, article mappings, and run records between runs.

---

## Source: Heretto Deploy

Reads from the **Heretto Deploy API v4** and maps each content item into an `IRPage`.

- Incremental sync via `/changed_content?since={cursor}` with audience-preference deduplication
- Full resync via recursive `/structure` tree traversal
- Parses `customMetadata.taxonomy` into per-group `IRTaxonomyValue` lists
- Extracts standard metadata: title, short description, content type, last-modified timestamp
- Binary asset download via short-lived JWT URLs embedded in article HTML
- Changeset deduplication by `fileUuid`; separates `removed` from `changed` entries

**Credential fields:**

| Field | Description |
|-------|-------------|
| `api_key` | Deploy API key (sent as `X-Deploy-API-Auth`) |
| `base_url` | Deploy base URL, e.g. `https://myorg.deploy.heretto.com` |
| `audience` | Preferred audience for deduplication (default: `private`) |

---

## Target Connectors

### Salesforce Knowledge (`connector_id: salesforce`)

Publishes articles to Salesforce Knowledge using the REST API. Supports the full draft → publish workflow with idempotent upserts via a custom external ID field.

- OAuth 2.0 client credentials flow (auto-refresh on 401)
- Idempotent upserts via `external_id_field` (default: `Heretto_UUID__c`)
- HTML sanitized to the Knowledge-approved tag whitelist
- Binary images uploaded as Salesforce ContentVersions and rewritten in HTML
- Deferred cross-article link fixup after all articles are loaded
- Data Category sync: maps Deploy taxonomy groups to SF `Knowledge__DataCategorySelection` child records
- Configurable `knowledge_type` (default: `Knowledge__kav`)

**Credential fields:** `instance_url`, `client_id`, `client_secret`, `api_version`, `knowledge_type`, `external_id_field`

---

### Noop (`connector_id: noop`)

A pass-through connector for testing. Accepts all articles without writing anywhere. No credentials required.

---

## Sync Configuration

### Field Mapping

Maps Deploy IR fields to target system fields. Keys are source field names; values are the target field API names.

```json
{
  "title":             "Title",
  "short_description": "Summary",
  "html_body":         "Content__c"
}
```

**Available source fields:**

| IR field | Deploy source | Notes |
|----------|---------------|-------|
| `title` | top-level `title` | |
| `short_description` | `shortDescription` | |
| `html_body` | `content` | Sanitized before upload |
| `content_type` | `standardMetadata.text_single_Line.contentType` | |
| `last_modified_iso` | `standardMetadata.date.lastModified` | ISO 8601 |
| `taxonomy` | `customMetadata.taxonomy` | Used for category sync, not field mapping |

### Data Category Mapping (Salesforce only)

Maps Deploy taxonomy group names to SF data category group API names. Stored as `category_map` within the mapping JSON.

```json
{
  "category_map": {
    "Audiences": "Audiences",
    "Accounts":  "Products"
  }
}
```

SF data category groups must be configured in Salesforce Setup before this mapping takes effect. Categories are synced after upsert and before publish.

### Scheduling

Each sync has a cron expression that controls automatic runs. Any standard cron expression is supported.

```
0 9 * * *      # Daily at 9 AM
*/30 * * * *   # Every 30 minutes
0 6 * * 1-5    # Weekdays at 6 AM
```

---

## Managing Syncs (UI)

The web UI (Angular, port `4200` in development) provides:

- **Dashboard** — overview of all active syncs and recent run status
- **Create / Edit sync** — configure adapter, connector, credentials, cron schedule, field mapping, and data category mapping
- **Sync Changes** — trigger an incremental run immediately
- **Full Resync** — trigger a structure-walk run that fetches every topic, bypassing the change cursor
- **Run history** — per-run status, timestamps in the viewer's local timezone, article counts, and error messages
- **Delete sync** — removes the sync and unregisters its schedule

The UI includes two administration pages provided by the hop-core platform layer:

- **Administration** (`/admin`) — organization management: members, invitations, and org settings. Visible to org admins and superusers.
- **System Admin** (`/superadmin`) — currently shows the same organization management page as Administration. This page is reserved for platform-level superuser functionality. The Heretto team plans to add additional connector endpoints — such as ServiceNow and Zendesk — in the future; when that happens, System Admin will be where connector registration and cross-org configuration are managed. Until then, the two pages are intentionally identical.

---

## API Reference

All routes are mounted under `/api/v1` and require a valid JWT. Routes are org-scoped.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/syncs` | List all active syncs for the org |
| `POST` | `/syncs` | Create a new sync configuration |
| `GET` | `/syncs/{id}` | Get a single sync by ID |
| `PUT` | `/syncs/{id}` | Update name, cron, deployment, credential, or mapping |
| `DELETE` | `/syncs/{id}` | Delete sync and remove its schedule |
| `POST` | `/syncs/{id}/trigger` | Trigger an incremental run |
| `POST` | `/syncs/{id}/trigger?force_full=true` | Trigger a force full resync |
| `GET` | `/syncs/{id}/runs` | List recent runs (default last 20) |
| `GET` | `/syncs/{id}/records` | List synced article records; filter by `record_status` |

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 24+
- [hop-core](https://github.com/Heretto/hop-core) — must be cloned and installed before the syndication service

### Required directory layout

Both repos must be siblings under the same parent directory. This is required for the Docker build and for the frontend SCSS theme imports.

```
parent-dir/
├── hop-core/
└── syndication-service/
```

### 1 — Install hop-core

```bash
git clone https://github.com/Heretto/hop-core.git
pip install ./hop-core
```

### 2 — Build hop-ui (required for the frontend)

```bash
cd hop-core/ui
npm install
npm run build
cd -
```

### 3 — Configure environment

```bash
cd syndication-service
cp .env.example .env
```

Open `.env` and set the three required keys before continuing:

| Variable | How to generate |
|----------|-----------------|
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `APP_SECRET_KEY` | Any random string ≥ 32 characters |
| `JWT_SECRET_KEY` | Any random string ≥ 32 characters |

All other values in `.env` have working defaults for local development.

### 4 — Run the backend

```bash
# From syndication-service/
pip install -e ".[dev]"

# Database migrations (SQLite by default — dev only)
# Set DATABASE_URL=postgresql+psycopg2://... for production
alembic upgrade head

uvicorn syndication.main:app --reload --port 8000
```

### 5 — Create the first admin account

```bash
python scripts/seed.py
```

You will be prompted for an email address and password. The password must be at least 12 characters and include an uppercase letter, a digit, and a special character. The script is idempotent — it does nothing if an admin account already exists.

### 6 — Run the frontend (separate terminal)

```bash
cd syndication-service/frontend
npm install
npm start          # http://localhost:4200, proxies /api → :8000
```

### 7 — Run the tests

```bash
pytest tests/
```

### Docker Compose

Requires the same sibling directory layout above. Run from within `syndication-service/`:

**Option A — auto-create admin at startup (recommended for first install)**

Add `ADMIN_EMAIL` and `ADMIN_PASSWORD` to your `.env` before starting. On first boot the backend creates the admin account automatically and logs `Auto-seed: created admin account`.

```bash
# In .env (or export before running docker compose):
ADMIN_EMAIL=you@yourcompany.com
ADMIN_PASSWORD=YourStr0ng!Password
```

```bash
bash scripts/docker-up.sh
```

`docker-up.sh` also auto-generates any missing secret keys (`APP_SECRET_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`) and warns if `ADMIN_EMAIL` is not set.

**Option B — create admin interactively after startup**

```bash
docker compose up --build
docker compose exec backend python scripts/seed.py
```

> Credentials are stored encrypted using hop-core's Fernet layer. The `ENCRYPTION_KEY` must be a valid Fernet key (32 url-safe base64-encoded bytes) — any other value causes an immediate startup crash.

---

## Troubleshooting

**App is running but I can't log in — no account exists**

Run the seed script to create the first admin account:

```bash
# Local dev
python scripts/seed.py

# Docker
docker compose exec backend python scripts/seed.py
```

Alternatively, set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` and restart — the account will be created automatically on next startup.

---

**Registration fails with "default organization not found"**

This means `SINGLE_ORG_MODE=true` but the organization row is missing. Restart the backend — it creates the default organization automatically on startup.

---

**`ENCRYPTION_KEY` startup crash**

The key must be a valid Fernet key (exactly 32 url-safe base64-encoded bytes). Generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
