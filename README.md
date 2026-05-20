# Relic

Relic is a storage control plane for organizing files across S3-compatible
object stores. It presents a permissioned virtual filesystem to users, stores
file bytes in registered bucket backends, and gives admins tools to manage
users, access, storage tiers, and bucket health.

At a high level, Relic separates logical files from physical blobs:

- Users browse folders, upload files, search metadata, and download objects.
- Admins register storage buckets, grant recursive folder permissions, and
  manage users and SigV4 access keys.
- The backend deduplicates identical content by hash, tracks blob reference
  counts, and places bytes into tiered storage backends.
- A **maintenance** worker path runs cleanup, bucket probing, and lifecycle
  migration.

## Current Features

### Filesystem

- Virtual folder tree with root and nested folders.
- Folder create, rename, move, copy, and delete operations.
- File upload, download, rename, move, copy, and delete operations.
- Drag-and-drop folder movement in the UI.
- Native file drop uploads into the selected folder.
- Breadcrumb navigation, folder tree sidebar, sortable folder contents, and
  paginated file listings.
- File detail pages with metadata, tags, keywords, key/value fields, metadata extraction
  status, uploader, timestamps, and quick links into search.

### Search and Metadata

- Global search across visible files by name, original filename, summary,
  tags, and keywords.
- Faceted filters for tags, MIME types, extensions, and metadata key names.
- Key/value filters with equality and numeric comparison operators.
- Folder-scoped search, including recursive search.
- Filters for size, uploader, created date range, MIME type, extension,
  keywords, and tags.
- Sortable, paginated results.
- Command-palette style search suggestions for files and folders.
- Canonical file metadata schema with size, extension, MIME type, original
  filename, tags, keywords, summary, and scalar key/value metadata.

### Blob metadata at ingest

MIME type and extension are detected from file bytes at upload time
(`domain/blobs/sniff.py`). Consumer-owned JSON metadata lives on `File.meta`
and is searchable via the control-plane search API.

### Storage

- S3-compatible bucket backends with encrypted credentials.
- Bucket tiers: hot, warm, cold, and frozen.
- Capacity-aware placement for new blobs.
- Bucket health probes for PUT, HEAD, GET, and DELETE latency.
- Content-hash deduplication with blob reference counts.
- Metadata-only copies that point multiple logical files at the same blob.
- Deferred purge of dereferenced blob bytes.
- Folder-level storage policy with inherited minimum tier and cooldown days.
- Background rebalance jobs that can move blobs to colder tiers after cooldown
  or away from pressured buckets.

### Access Control

- Cookie-based web sessions.
- User and admin roles.
- Recursive folder grants with read, write, delete, and enrich permissions.
- Admin screens for users, folder grants, buckets, and access keys.
- SigV4 access keys for S3-style API access.

### Audit log

Unified `audit_events` records actor-driven admin actions and storage
maintenance outcomes (blob purges, migrations, bucket probes, retention
trims). The admin audit log UI filters by operation, status, request ID,
actor, and time range.

Retention is controlled by `EVENT_RETENTION_DAYS`; the maintenance worker
trims old rows on its cron tick.

### Operational Visibility

- Admin view for audit events is live.
- Prometheus-compatible `GET /metrics` on the API process (not under `/api`).
  Low-cardinality counters and histograms in `server/infra/metrics.py`:
  - `relic_api_requests_total` / `relic_api_duration_seconds` — HTTP API
    traffic by method, route template, and status class (`2xx`, `4xx`, …).
  - `relic_gateway_requests_total` / `relic_gateway_duration_seconds` — S3
    gateway traffic under `/s3` by operation (e.g. `put_object`, `get_object`).
  - `relic_maintenance_jobs_total` / `relic_maintenance_duration_seconds` —
    maintenance worker jobs by name and outcome.
  - `relic_maintenance_queue_depth` — pending jobs on the maintenance ARQ queue.
  - `relic_storage_backend_probe_total` — bucket probe successes and failures.
  Standard `prometheus-client` process metrics are included in the scrape body.

### Health and Readiness

- `/healthz` reports basic API process liveness.
- `/readyz` checks database connectivity, Redis queue connectivity,
  object-store probe state, and configuration warnings.
- Object-store readiness uses the latest bucket probe state; the maintenance
  worker runs remote PUT/HEAD/GET/DELETE checks.

### API and S3 Gateway

- FastAPI JSON API under `/api`.
- Presigned upload, download, delete, and copy URLs.
- Path-style S3 gateway under `/s3`.
- Implemented object operations: `PutObject`, `CopyObject`, `HeadObject`,
  `GetObject`, and `DeleteObject`.
- Range GET support for downloads.
- Service and bucket operations: `ListBuckets`, `HeadBucket`, and
  `ListObjectsV2`.
- Multipart upload lifecycle: create upload, upload part, complete, and abort.
- Native SigV4 `Authorization` header authentication for path-style boto3,
  botocore, and AWS CLI style clients using Relic access keys.

Relic still supports its presigned SigV4 query URL contract for web/API upload
and download flows. Native clients should use path-style addressing and set
their region to `RELIC_SIGNING_REGION` (default: `relic`), for example:

```python
import boto3
from botocore.client import Config

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:8000/s3",
    aws_access_key_id="RK...",
    aws_secret_access_key="...",
    region_name="relic",
    config=Config(s3={"addressing_style": "path"}),
)
```

Access keys created before native S3 auth stored only a one-way secret hash and
must be reissued before they can authenticate native clients.

## Architecture

Relic is split into a React client, a FastAPI server, and ARQ workers:

- `client/` is a Vite, React, TypeScript, Tailwind, and shadcn/ui app.
- `server/api/` contains the HTTP API and S3 gateway routes.
- `server/application/` contains use cases (control plane, gateway, maintenance).
- `server/domain/` contains pure business rules (naming, meta, paths, sniffing).
- `server/ports/` defines store and adapter interfaces.
- `server/infra/` contains SQLAlchemy stores, object storage adapters, auth, cache, and maintenance.
- `server/composition.py` wires the Unit of Work from settings.
- PostgreSQL stores users, folders, files, blobs, access grants, access keys,
  bucket registrations, and audit events. SQLite is used in tests.
- Redis backs ARQ maintenance jobs on the `relic:maintenance` queue.
- Garage is used by the local Docker setup as two S3-compatible object stores,
  one hot and one cold.

## Local Development

The repository includes a Docker Compose stack for the full local product:

- PostgreSQL.
- Redis.
- API server.
- Maintenance worker for storage cleanup, bucket probes, and lifecycle jobs.
- React client served by nginx.
- Two Garage object-store instances.
- Garage web UIs for both object stores.

Start the stack:

```bash
docker compose up --build
```

The compose stack runs migrations and seeds the root folder plus an admin user
before starting the API.

Default local URLs:

- Client: <http://localhost:3000>
- API: <http://localhost:8000>
- Garage hot S3 API: <http://localhost:3900>
- Garage hot web UI: <http://localhost:3909>
- Garage cold S3 API: <http://localhost:3910>
- Garage cold web UI: <http://localhost:3919>

Default seeded admin credentials:

```text
Email: admin@relic.local
Password: relic-admin
```

These defaults are for local development only. Override secrets and seed values
with environment variables before using non-local data.

## Useful Commands

Backend commands use `uv` and require Python 3.14 or newer.

Run the client locally:

```bash
cd client
npm install
npm run dev
```

Build, typecheck, or lint the client:

```bash
cd client
npm run build
npm run typecheck
npm run lint
```

Run backend tests:

```bash
cd server
uv run pytest
```

Run migrations manually:

```bash
cd server
uv run alembic upgrade head
```

Run the API manually:

```bash
cd server
uv run uvicorn api.app:app --reload
```

Run the maintenance worker manually:

```bash
cd server
uv run arq workers.maintenance.WorkerSettings
```

Run the live S3 gateway compatibility smoke harness:

```bash
cd server
uv run python compat/s3_gateway_compat.py
```

This expects the local stack to be running at `http://localhost:8000`, the
seeded admin login to work, and at least one physical bucket backend to be
registered. The harness creates a temporary top-level folder, uploads a few
objects through Relic presigned PUT URLs, verifies `ListBuckets`, `HeadBucket`,
`ListObjectsV2`, multipart upload, `HeadObject`, and `GetObject`, then creates a
Relic access key and repeats representative object, listing, and multipart flows
through a native boto3 client. Use `--api-url`, `--email`, `--password`,
`--bucket-name`, or `--keep-data` to override defaults.

## Configuration

Important environment variables include:

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
  `POSTGRES_PASSWORD`, or `DATABASE_URL` to override the connection string.
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`.
- `ENCRYPTION_SECRET` for encrypted bucket credentials.
- `SESSION_SECRET`, `SESSION_COOKIE_NAME`, `SESSION_MAX_AGE_SECONDS`, and
  `SESSION_COOKIE_SECURE`.
- `RELIC_ADMIN_NAME`, `RELIC_ADMIN_EMAIL`, and `RELIC_ADMIN_PASSWORD` for seed
  data.
- `RELIC_SIGNING_TTL_SECONDS`, `RELIC_SIGNING_REGION`,
  `RELIC_SIGNING_KEY_ID`, `RELIC_SIGNING_SECRET`, `RELIC_SIGNING_KEYS`, and
  `RELIC_SIGNING_CURRENT_KEY_ID` for S3 gateway signing. Native S3 clients must
  sign with the same `RELIC_SIGNING_REGION`.
- `meta_extract` per-toolchain byte caps such as `IMAGE_META_EXTRACT_MAX_BYTES`,
  `PDF_META_EXTRACT_MAX_BYTES`, `TEXT_META_EXTRACT_MAX_BYTES`, and related
  per-format limits. Files larger than the cap are parsed from the truncated
  prefix.
- `PROCESSING_QUEUE_NAME` and `MAINTENANCE_QUEUE_NAME` for the two ARQ worker
  queues.
- `DISPATCHER_BATCH_SIZE`, `DISPATCHER_SAFETY_INTERVAL_SECONDS`, and
  `DISPATCHER_LISTEN_BACKOFF_SECONDS` to tune the warm-path dispatcher.
- `EVENT_RETENTION_DAYS` — retention knob for `audit_events`. Per-table
  retention can be split out later if it becomes necessary.
- Storage maintenance knobs such as `STORAGE_MAINTENANCE_PURGE_BATCH`,
  `STORAGE_MAINTENANCE_MIGRATE_BATCH`, and
  `STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO`.

## Product Status

Relic is an early product with substantial core behavior in place. The web
app, JSON API, object gateway, native SigV4 clients, content-hash
deduplication, tiered storage placement, unified `audit_events`, Prometheus
`/metrics`, and production health / readiness endpoints are live. Planned work
includes external activity sinks, import-from-bucket flows, quotas, extended
retention controls, versioning, and richer admin file/blob inspection.
