# Syndication Service

A pipeline that syncs DITA content from Heretto Deploy to external knowledge bases — Salesforce Knowledge, Zendesk Guide, and ServiceNow — on a schedule or on demand.

---

## Architecture

The service is built around three layers:

```
Heretto Deploy (source adapter)
        ↓
  IR Pipeline (runner)
        ↓
  Target Connector (salesforce | zendesk | servicenow | noop)
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

### Zendesk Guide (`connector_id: zendesk`)

Publishes articles to a Zendesk Help Center section using label-based identity.

- Bearer token auth
- Label-based upsert: each article tagged `heretto-{uuid}` on creation
- Publishes to a configured `section_id` within the Help Center
- HTML sanitized before upload
- Locale-aware (`en-us` default, configurable)

**Credential fields:** `subdomain`, `access_token`, `section_id`, `locale`

---

### ServiceNow Knowledge (`connector_id: servicenow`)

Writes articles to the ServiceNow `kb_knowledge` table via the Table API.

- Bearer token auth
- Idempotent upserts via a custom external ID field (default: `u_external_id`)
- Publish via `workflow_state → published`
- Archive via `workflow_state → retired`
- Configurable knowledge base (`knowledge_base_sys_id`) and default category (`kb_category_sys_id`)

**Credential fields:** `instance_url`, `access_token`, `knowledge_base_sys_id`, `kb_category_sys_id`, `external_id_field`

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

**Prerequisites:** Python 3.11+, Node.js 24+, a `.env` file with hop-core settings.

```bash
# Backend
pip install -e ".[dev]"
uvicorn syndication.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm start          # http://localhost:4200, proxies /api → :8000

# Database migrations
alembic upgrade head

# Tests
pytest tests/
```

> Credentials are stored encrypted using hop-core's Fernet layer. The encryption secret key must be set in the environment before the service can decrypt credentials at runtime.
