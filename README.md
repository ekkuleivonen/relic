# Relic

Relic is a storage control plane for organizing files across S3-compatible
object stores. It presents a permissioned virtual filesystem to users, stores
file bytes in registered bucket backends, extracts searchable metadata in the
background, and gives admins tools to manage users, access, storage tiers, and
bucket health.

At a high level, Relic separates logical files from physical blobs:

- Users browse folders, upload files, search metadata, and download objects.
- Admins register storage buckets, grant recursive folder permissions, and
  manage users and SigV4 access keys.
- The backend deduplicates identical content by hash, tracks blob reference
  counts, and places bytes into tiered storage backends.
- Background **processors** enrich files with searchable metadata (today: the
  `meta_extract` substrate, with more substrates planned), and a separate
  **maintenance** path runs cleanup, bucket probing, and lifecycle migration.

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

### Metadata Extraction

Uploaded and copied files are queued for asynchronous metadata extraction via
the `meta_extract` processor substrate. It currently detects or enriches
metadata for:

- Images.
- CSV files.
- JSON and JSONL files.
- PDFs.
- Parquet files.
- Audio files.
- Video files.
- Office documents.
- HTML and XHTML.
- Archives.
- Plain text and other readable text formats.

Processor output is merged with upload-time metadata while preserving
user-provided values where they overlap.

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

### Event Log and Processors

Relic runs its background work on three concurrency tiers, separated by
audience and write path:

- **Hot path** — the synchronous S3 gateway and JSON API. Mutates canonical
  tables, emits events in the same transaction, returns. Does not own any
  async work; it only produces the triggers other tiers consume.
- **Warm path** (`relic:processing` queue) — runs event-driven processor
  substrates. The seeded `meta_extract` substrate enriches `File.meta`
  today; future substrates (preview, thumbnail, external sinks) land as
  siblings.
- **Cold path** (`relic:maintenance` queue) — runs scheduled batches such as
  purge dereferenced blobs, bucket probes, blob rebalance, and event
  retention trim. Invisible to external consumers.

The two queues are separate worker pools so a slow rebalance can never block
fast metadata extraction.

#### Event tables

- `audit_events` (live) — actor-driven log for identity, access, bucket,
  folder admin changes, and processor cursor changes (`processor.created`,
  `processor.updated`, `processor.deleted`, `processor.enabled`,
  `processor.disabled`, `processor.cursor.rewound`,
  `processor.cursor.skipped`). Written in the same DB transaction as the
  canonical mutation. Envelope is intentionally narrow:
  `(id, created_at, updated_at, operation, status, actor_user_id,
  request_id, meta)` — resource ids that an event refers to live inside
  `meta`. The admin audit log UI filters by operation, status, request ID,
  actor, and time range with per-row metadata detail.
- `file_events` (live) — durable content activity log and the warm-path
  outbox. Carries `file.*`, `folder.*`, and `processor.<substrate>.*`
  events. File and folder mutations write this table in the same
  transaction as the canonical change; the per-row monotonic `offset` is the
  replay primitive. Admins can browse the full log on the File Events page.
- `processors` (live) — registry holding identity, config, enabled state,
  and the `last_committed_offset` cursor for every warm-path subscriber
  (internal substrates today, external sinks planned). The Processors admin
  page surfaces cursor lag, lets admins pause/resume runs, and exposes
  auditable rewind and skip-stuck-event actions.
- `maintenance_events` (live) — internal-only log of cold-path resource
  outcomes such as blob purges, migrations, bucket probes, and event
  retention trims. Never delivered to external sinks. The Maintenance Events
  admin page filters by job, action, status, batch ID, bucket ID, blob ID,
  and time range.

`maintenance_events` rows are emitted by `worker_maintenance` jobs. They are
resource-level outcomes, not batch summaries; `batch_id` groups every row
from one cron firing. The table envelope is `(id, created_at, job, action,
status, batch_id, bucket_id, blob_id, duration_ms, meta)`. `bucket_id` is a
nullable FK with `ON DELETE SET NULL`; `blob_id` is deliberately not a
foreign key because purge events often describe blob rows that no longer
exist. Current actions are:

- `purge_dereferenced_blobs`: `blob.purged`, `blob.purge_failed`.
- `rebalance_blob_storage`: `blob.migrated`, `blob.migration_skipped`,
  `blob.migration_failed`.
- `bucket_probe`: `bucket.probe_ok`, `bucket.probe_failed`.
- `trim_audit_events`: `audit.trimmed`.
- `trim_file_events`: `file_event.trimmed`.
- `trim_maintenance_events`: `maintenance_event.trimmed`.

High-volume object reads (`GET`, `HEAD`, signed-URL fetches) deliberately do
not write event rows; their performance lives in Prometheus aggregates only.

Retention across all event tables is controlled by `EVENT_RETENTION_DAYS`.
The maintenance worker trims rows older than that age during its regular
cron tick. The trim refuses to delete `file_events` rows past
`min(processors.last_committed_offset)` across enabled processors, so a
paused or rewound processor can never lose events out from under it.
`processors` is registry data and is not subject to retention.

#### Warm-path dispatcher

Warm processors do not subscribe to API hooks; they subscribe to
`file_events` through their own cursor on the `processors` table. The
dispatcher is pull-based:

1. Listens on the Postgres `file_event_emitted` channel via `LISTEN/NOTIFY`
   for wake-up, plus a safety-net tick every `DISPATCHER_SAFETY_INTERVAL_SECONDS`.
2. For each enabled processor, selects the oldest `file_events` row past
   `last_committed_offset` whose `event_type` is in
   `subscribed_event_types`. Unsubscribed events never reach a worker.
3. Enqueues one warm-queue job with `_job_id = f"{processor_id}:{event_id}"`,
   relying on arq's built-in dedup so a re-tick is safe.
4. Does not advance the cursor on enqueue. The worker advances it only
   after the handler returns successfully, inside the same DB transaction as
   any canonical mutation the handler made.

The contract every warm processor inherits:

- **Cursor-on-success.** A failing event halts its processor's cursor until
  an admin intervenes. The escape hatch is a `processor.cursor.skipped`
  audit row written when an admin advances the cursor past a poison-pill
  event. Every skip is auditable; there is no silent forward-jump.
- **Head-of-line blocking is accepted.** The trade-off for a simple,
  durable, replayable cursor model.
- **Idempotency over `event_id`.** Handlers must produce the same observable
  result on a second run for the same event ID. `meta_extract` overwrites
  `File.meta` deterministically; external sinks must use a downstream
  idempotency key.
- **Per-processor concurrency = 1.** Enforced by `LIMIT 1` per processor in
  the dispatcher, by `_job_id` dedup in arq, and by `SELECT ... FOR UPDATE`
  on the processor row inside the worker. The processing worker also pins
  `max_jobs = 1` as defense-in-depth. Parallelism comes from running more
  worker pods, not more concurrent jobs per worker.
- **Processor outcome events.** Workers emit
  `processor.<substrate>.completed` or `processor.<substrate>.failed` to
  `file_events` so external consumers can react to "metadata is now ready"
  the same way internal subscribers do.

#### Processor substrates

A substrate is the warm-path handler for one `processors.kind`. Today there
is one shipping substrate:

- `meta_extract` — reads bytes from object storage (capped per toolchain via
  `*_META_EXTRACT_MAX_BYTES`), runs the matching toolchain (image, PDF,
  CSV, JSON, parquet, audio, video, office-doc, archive, HTML, text), and
  writes the result to `File.meta`.

New substrates plug in by registering a `kind`, a pydantic config model,
and a handler. First-party substrates are upserted from `server/seed.py`;
admin-managed substrates (future external sinks) are created from the API.

### Operational Visibility

- Admin views for audit events, file events, maintenance events, and
  processors are live.
- Processor admin includes enabled state, cursor lag, pause/resume, rewind,
  and skip-stuck-event actions, with cursor changes written to `audit_events`.

Prometheus-compatible `/metrics` is not implemented yet; it remains tracked in
`ROADMAP.md` alongside lower-level gateway, API, processor, and maintenance
metrics.

### Health and Readiness

- `/healthz` reports basic API process liveness.
- `/readyz` checks database connectivity, Redis queue connectivity, processor
  registry access, object-store probe state, and configuration warnings.
- Readiness includes queue depth and oldest pending job age for the
  `relic:processing` and `relic:maintenance` queues.
- Object-store readiness uses the latest bucket probe state; the probe worker
  remains responsible for doing remote PUT/HEAD/GET/DELETE checks.

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

The S3 gateway still uses Relic presigned SigV4 query URLs for the supported
flows. Native AWS CLI, boto3 client, rclone, and DuckLake compatibility checks
should be added after the gateway accepts normal access-key `Authorization`
header requests.

## Architecture

Relic is split into a React client, a FastAPI server, and ARQ workers:

- `client/` is a Vite, React, TypeScript, Tailwind, and shadcn/ui app.
- `server/api/` contains the HTTP API and S3 gateway routes.
- `server/services/` contains the filesystem, object, bucket, search, access,
  placement, audit event, file event, processor, and maintenance logic.
- `server/processors/` contains the warm-path runtime: the substrate
  registry, the `meta_extract` substrate and its toolchains, the arq workers
  for processing and maintenance, and the pull-based dispatcher that
  consumes `file_events` and feeds the warm queue.
- PostgreSQL stores users, folders, files, blobs, access grants, access keys,
  bucket registrations, durable event tables, and the processor registry. The
  dispatcher uses Postgres `LISTEN/NOTIFY` on `file_event_emitted` to wake up
  promptly when new events land.
- Redis backs ARQ processor and maintenance jobs. The warm `relic:processing`
  queue and cold `relic:maintenance` queue run as separate worker pools so a
  slow rebalance batch never delays metadata extraction.
- Garage is used by the local Docker setup as two S3-compatible object stores,
  one hot and one cold.

## Local Development

The repository includes a Docker Compose stack for the full local product:

- PostgreSQL.
- Redis.
- API server.
- Processing worker for metadata extraction.
- Dispatcher that converts new `file_events` rows into warm-queue jobs.
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

Run the processing worker manually:

```bash
cd server
uv run arq processors.worker_processing.WorkerSettings
```

Run the maintenance worker manually:

```bash
cd server
uv run arq processors.worker_maintenance.WorkerSettings
```

Run the dispatcher manually:

```bash
cd server
uv run python -m processors.dispatcher
```

Run the live S3 gateway compatibility smoke harness:

```bash
cd server
uv run python compat/s3_gateway_compat.py
```

This expects the local stack to be running at `http://localhost:8000`, the
seeded admin login to work, and at least one physical bucket backend to be
registered. The harness creates a temporary top-level folder, uploads a few
objects through Relic presigned PUT URLs, and verifies `ListBuckets`,
`HeadBucket`, `ListObjectsV2`, multipart upload, `HeadObject`, and `GetObject`
against the live gateway. Use `--api-url`, `--email`, `--password`,
`--bucket-name`, or `--keep-data` to override defaults.

Current limitation: the harness uses Relic's presigned SigV4 query URL contract.
Native AWS CLI, boto3 client, rclone, and DuckLake checks should be added after
the gateway accepts normal access-key `Authorization` header requests.

## Configuration

Important environment variables include:

- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
  `POSTGRES_PASSWORD`.
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`.
- `ENCRYPTION_SECRET` for encrypted bucket credentials.
- `SESSION_SECRET`, `SESSION_COOKIE_NAME`, `SESSION_MAX_AGE_SECONDS`, and
  `SESSION_COOKIE_SECURE`.
- `RELIC_ADMIN_NAME`, `RELIC_ADMIN_EMAIL`, and `RELIC_ADMIN_PASSWORD` for seed
  data.
- `RELIC_SIGNING_TTL_SECONDS`, `RELIC_SIGNING_REGION`,
  `RELIC_SIGNING_KEY_ID`, `RELIC_SIGNING_SECRET`, `RELIC_SIGNING_KEYS`, and
  `RELIC_SIGNING_CURRENT_KEY_ID` for presigned S3 gateway URLs.
- `meta_extract` per-toolchain byte caps such as `IMAGE_META_EXTRACT_MAX_BYTES`,
  `PDF_META_EXTRACT_MAX_BYTES`, `TEXT_META_EXTRACT_MAX_BYTES`, and related
  per-format limits. Files larger than the cap are parsed from the truncated
  prefix.
- `PROCESSING_QUEUE_NAME` and `MAINTENANCE_QUEUE_NAME` for the two ARQ worker
  queues.
- `DISPATCHER_BATCH_SIZE`, `DISPATCHER_SAFETY_INTERVAL_SECONDS`, and
  `DISPATCHER_LISTEN_BACKOFF_SECONDS` to tune the warm-path dispatcher.
- `EVENT_RETENTION_DAYS` — single retention knob applied to every event table
  (`audit_events`, `file_events`, and `maintenance_events`). Per-table
  retention can be split out later if it becomes necessary.
- Storage maintenance knobs such as `STORAGE_MAINTENANCE_PURGE_BATCH`,
  `STORAGE_MAINTENANCE_MIGRATE_BATCH`, and
  `STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO`.

## Product Status

Relic is an early product with substantial core behavior in place. The web
app, JSON API, object gateway, content-hash deduplication, tiered storage
placement, `audit_events`, `file_events`, the `processors` registry, the
`maintenance_events` cold-path log, the `LISTEN/NOTIFY` warm-path
dispatcher, the seeded `meta_extract` substrate, and production health /
readiness endpoints are all live and developed against. Still tracked in
`ROADMAP.md`: external activity sinks (webhook, SQS, Kafka, object-store),
native-client S3 compatibility work, Prometheus metrics endpoint,
import-from-bucket flows, quotas, retention, versioning, and richer admin
file/blob inspection beyond the current placeholder UI pages.
