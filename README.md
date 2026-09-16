# Syndication Service

A pipeline that syncs DITA content from Heretto Deploy to Salesforce Knowledge on a schedule or on demand. If your team authors content in Heretto and needs to deliver it through Salesforce Knowledge, this service automates that handoff, keeping your knowledge base current without manual export or copy-paste.

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- A Heretto Deploy API key and deployment ID
- A Salesforce org with Knowledge enabled

---

## Install

Clone the project:

```bash
git clone https://github.com/Heretto/syndication-service.git
cd syndication-service
./install.sh
```

`install.sh` installs Python and npm dependencies, generates required secrets, runs database migrations, and creates the first admin account.

To adjust any defaults (database URL, SMTP, admin email, etc.), open `.env` — it is created from `.env.example` during install with all available options documented inline.

---

## Usage

Run locally using a simple shell script:

```bash
./dev.sh
```

This starts the backend on `http://localhost:8000` and the frontend on `http://localhost:4200`. Press `Ctrl+C` to stop both.

---

## Features

- **Incremental and full syncs** — incremental runs use a high-water-mark cursor so only changed content since the last sync is processed; full resyncs walk the entire deployment structure
- **Removed content handling** — full resyncs detect articles whose source topic no longer exists and automatically archive (Online) or delete (Draft) them in Salesforce Knowledge
- **Publish modes** — auto-publish articles to Online on sync, or leave them as Drafts for manual review
- **Field mapping** — map Heretto content areas (short description, content body, etc.) to any writable Salesforce Knowledge fields that are configured
- **Data category mapping** — map Heretto taxonomy structures to Salesforce Knowledge data category groups for article visibility control or article metadata
- **Scheduled and on-demand** — any standard cron expression, plus manual trigger from the UI
- **Live progress tracking** — running syncs show a real-time progress bar ("x of y completed") in the UI
- **Run warnings** — non-fatal issues (failed archives, Salesforce article limit hits) are grouped into a single summary warning
- **Credential management** — Salesforce credentials stored encrypted; supports OAuth 2.0 Client Credentials Flow (auto-refresh) or static access token

---

## First Sync

**Before you start — Salesforce setup required:**

- Create a custom text field on your Knowledge object to store the Heretto article UUID (e.g. `Heretto_UUID__c`). This is the idempotency key the service uses to identify articles across syncs.
- For OAuth authentication (recommended): create a Salesforce External Client App with Client Credentials Flow enabled and assign a Run As user. For a static token, a valid Salesforce access token is sufficient.

After running `./dev.sh`:

1. Log in and go to **Credentials → New credential**. Enter your Salesforce instance URL, API version, Knowledge object API name (e.g. `Knowledge__kav`), the external ID field you created above, and either your OAuth client credentials or a static access token.
2. Go to **Syncs → New Sync**. Enter the Heretto deployment ID, select the credential, configure a schedule or leave it as manual, and map at least one source field (e.g. `title → Title`).
3. Click **Full Resync** to push all current content from the deployment to Salesforce Knowledge.

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
| 7 | Publish | Make articles visible to end users (skipped in draft-only mode) |
| 8 | Archive removed | Detect and archive/remove stale articles (force full only — see below) |
| 9 | Deferred link fixup | Rewrite cross-article links after all articles are loaded |

### Incremental Sync

Uses the Deploy `/changed_content` endpoint with a **high-water-mark cursor**. Only articles with a `contentModificationDate` newer than the last successful sync are fetched. The cursor advances after each successful sync.

### Force Full Resync

Walks the complete `/structure` tree and fetches every topic regardless of modification date. Useful when articles exist in Deploy but were never emitted by the changeset endpoint (e.g. content published before sync tracking began). The high-water-mark cursor is **not** advanced after a forced resync.

A force full resync also performs **stale article detection**: after processing, it compares the set of articles just synced against every article previously mapped for this sync. Any mapped article whose source topic is no longer present is treated as removed:

- **Online (published) articles** — archived in Salesforce Knowledge via the `archiveKnowledgeArticles` standard action. The article is moved to Archived status and remains in Salesforce for a Knowledge admin to review or delete.
- **Draft articles** — deleted directly via the REST API.
- **Failures** — if archiving or deletion fails, a warning is recorded in the run record. The sync still completes with `success` status; warnings indicate items requiring manual follow-up in Salesforce.

> The pipeline is stateless. The executor layer is responsible for persisting the cursor, article mappings, and run records between syncs.

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
| `audience` | Preferred audience for deduplication. When set, articles matching this audience are preferred when the Deploy API returns duplicates across audience groups. Leave blank to receive all content regardless of audience.

---

## Target Connectors

### Salesforce Knowledge (`connector_id: salesforce`)

Publishes articles to Salesforce Knowledge using the REST API. Supports the full draft → publish workflow with idempotent upserts via a custom external ID field.

- OAuth 2.0 client credentials flow (auto-refresh on 401) or static access token
- Idempotent upserts via `external_id_field` (default: `Heretto_UUID__c`)
- HTML sanitized to the Knowledge-approved tag whitelist
- Binary images uploaded as Salesforce ContentVersions and rewritten in HTML
- Deferred cross-article link fixup after all articles are loaded
- Data Category sync: maps Deploy taxonomy groups to SF `Knowledge__DataCategorySelection` child records
- Configurable `knowledge_type` (default: `Knowledge__kav`)

**Authentication modes:**

| Mode | Fields required | Notes |
|------|-----------------|-------|
| OAuth 2.0 Client Credentials | `client_id`, `client_secret` | Recommended — token acquired and refreshed automatically. Requires a Salesforce External Client App with Client Credentials Flow enabled and a Run As user assigned. Leave `access_token` empty. |
| Static access token | `access_token` | Simpler but requires manual credential update when the token expires. Leave `client_id` and `client_secret` empty. |

**All credential fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `instance_url` | Always | Salesforce org base URL, e.g. `https://myorg.my.salesforce.com` |
| `api_version` | Always | REST API version, e.g. `65.0` |
| `knowledge_type` | Always | KAV object API name, e.g. `Knowledge__kav` |
| `external_id_field` | Always | Custom text field on the KAV object that stores the Heretto UUID, e.g. `Heretto_UUID__c` |
| `client_id` | OAuth only | Consumer Key from the External Client App |
| `client_secret` | OAuth only | Consumer Secret from the External Client App |
| `access_token` | Static only | Valid Salesforce access token |

---

### Noop (`connector_id: noop`)

A pass-through connector for testing. Accepts all articles without writing anywhere. No credentials required.

---

## Sync Configuration

### Field Mapping

Maps Deploy fields to target system fields. Keys are source field names; values are the target field API names.

```json
{
  "title":             "Title",
  "short_description": "Summary",
  "html_body":         "Content__c"
}
```

**Available source fields:**

| Deploy field | Deploy source | Notes |
|----------|---------------|-------|
| `title` | top-level `title` | |
| `short_description` | `shortDescription` | |
| `html_body` | `content` | Sanitized before upload |
| `content_type` | `standardMetadata.text_single_Line.contentType` | |
| `last_modified_iso` | `standardMetadata.date.lastModified` | ISO 8601 |
| `section_path` | structure traversal | Breadcrumb path, e.g. `Getting Started > Install`. Force full only. |
| `sort_order` | structure traversal | Numeric position within parent section. Force full only. |
| `taxonomy` | `customMetadata.taxonomy` | Used for category sync, not field mapping |

### Data Category Mapping (Salesforce only)

Maps Deploy taxonomy names to SF data category group API names. Stored as `category_map` within the mapping JSON.

```json
{
  "category_map": {
    "Audiences": "Audiences",
    "Accounts":  "Products"
  }
}
```

SF data category groups must be configured in Salesforce Setup before this mapping takes effect. Categories are synced after upsert and before publish.

### Publish Mode

Controls whether articles are published to Online status after upload, or left as drafts.

| Value | Behaviour |
|-------|-----------|
| `auto` (default) | After uploading each article, the service immediately publishes it to Online status in Salesforce Knowledge. Content is visible to end users as soon as the sync completes. |
| `draft` | Articles are uploaded and left in Draft status. A Salesforce Knowledge admin must review and publish them manually. |

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

- **Dashboard** — overview of all active syncs and recent sync activity
- **Create / Edit sync** — configure adapter, connector, credentials, cron schedule, publish mode, field mapping, and data category mapping
- **Sync Changes** — trigger an incremental run immediately
- **Full Resync** — trigger a structure-walk run that fetches every topic, bypassing the change cursor, and archives stale articles
- **Sync detail** — tabbed view (Recent Syncs | Configuration); running syncs show a live progress bar ("x of y completed"); completed runs display status, duration, article counts, and any warnings or errors in a table
- **Delete sync** — removes the sync and unregisters its schedule

The UI includes two administration pages provided by the hop-core platform layer:

- **Administration** (`/admin`) — organization management: members, invitations, and org settings. Visible to org admins and superusers.
- **System Admin** (`/superadmin`) — currently shows the same organization management page as Administration. This page is reserved for platform-level superuser functionality and will be where connector registration and cross-org configuration are managed as additional connectors are added. Until then, the two pages are intentionally identical.

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
| `POST` | `/syncs/{id}/trigger` | Trigger an incremental run (rate-limited: 10/min per IP) |
| `POST` | `/syncs/{id}/trigger?force_full=true` | Trigger a force full resync (same limit) |
| `GET` | `/syncs/{id}/runs` | List recent runs (default last 20, max 500) |
| `GET` | `/syncs/{id}/records` | List synced article records; filter by `record_status` |
| `GET` | `/fields/source` | List all mappable Deploy/IR source fields |
| `GET` | `/fields/target?credential_id=&connector_id=` | List writable fields from the target system (live, requires credential) |
| `GET` | `/fields/categories/target?credential_id=&connector_id=` | List Salesforce Data Category Groups (Salesforce only) |

---

## Running Locally

### Run the tests

```bash
pytest tests/
```

## Docker

Run from within `syndication-service/`. Both backend and frontend Docker builds are self-contained with no sibling repositories required.

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

> Credentials are stored encrypted using hop-core's Fernet layer. The `ENCRYPTION_KEY` must be a valid Fernet key (32 url-safe base64-encoded bytes). Any other value causes an immediate startup crash.

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

Alternatively, set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` and restart. The account will be created automatically on next startup.

---

**Registration fails with "default organization not found"**

This means `SINGLE_ORG_MODE=true` but the organization row is missing. Restart the backend. It creates the default organization automatically on startup.

---

**`ENCRYPTION_KEY` startup crash**

The key must be a valid Fernet key (exactly 32 url-safe base64-encoded bytes). Generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
