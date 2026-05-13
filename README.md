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
- File detail pages with metadata, tags, keywords, key/value fields, parse
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

Relic uses two event tables today and a processor registry, with one more
event table planned. They are deliberately separated by audience and write
path:

- `audit_events` (live) — actor-driven audit records for identity, access,
  bucket, folder admin changes, and processor cursor changes such as
  `processor.cursor.skipped`, `processor.cursor.rewound`, `processor.created`,
  `processor.updated`, and `processor.deleted`. Written in the same database
  transaction as the canonical mutation. Captures operation, status, actor,
  request ID, related file/folder/blob IDs, and operation-specific metadata.
  Surfaces in an admin audit log UI with filters for operation, status,
  request ID, actor, and time range, plus expandable per-event detail and an
  admin-only clear action for local/operational resets.
- `file_events` (live) — durable content activity log and outbox for
  `file.*`, `folder.*`, and `processor.<substrate>.*` events. File and
  folder mutations write this table in the same transaction as the canonical
  change. The dispatcher reads it through per-processor cursors; admins can
  browse the full log from the File Events page.
- `processors` (live) — registry table holding identity, config, enabled
  state, and the `last_committed_offset` cursor for every warm-path
  subscriber (internal substrates today, external sinks later). The seeded
  `meta_extract` row consumes file activity events and emits
  `processor.meta_extract.completed` / `processor.meta_extract.failed`
  outcomes back into `file_events`. The Processors admin page surfaces
  cursor lag, lets admins pause/resume runs, and exposes auditable
  rewind/skip-stuck-event actions.
- `maintenance_events` (planned, see `ROADMAP.md`) — internal-only log of
  cold-path resource outcomes such as blob purges and migrations. Never
  delivered to external sinks.

High-volume object reads (S3 `GET`, `HEAD`, signed-URL fetches) do not write
event rows; their performance is observable through Prometheus once the
metrics endpoint lands.

Retention across all event tables is controlled by `EVENT_RETENTION_DAYS`. The
maintenance worker trims rows older than that age during its regular cron
tick. `processors` is registry data and is not subject to retention; cursor
rewinds re-read whatever is still in `file_events` after the trim runs.

### API and S3 Gateway

- FastAPI JSON API under `/api`.
- Presigned upload, download, delete, and copy URLs.
- Path-style S3 gateway under `/s3`.
- Implemented object operations: `PutObject`, `CopyObject`, `HeadObject`,
  `GetObject`, and `DeleteObject`.
- Range GET support for downloads.

The S3 gateway is currently focused on object operations. Service and bucket
listing endpoints such as `ListBuckets`, `HeadBucket`, and `ListObjectsV2` are
stubbed and not ready for general S3 browser compatibility.

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
- `meta_extract` per-toolchain byte caps such as `IMAGE_PARSE_MAX_BYTES`,
  `PDF_PARSE_MAX_BYTES`, `TEXT_PARSE_MAX_BYTES`, and related per-format limits.
- `PROCESSING_QUEUE_NAME` and `MAINTENANCE_QUEUE_NAME` for the two ARQ worker
  queues.
- `DISPATCHER_BATCH_SIZE`, `DISPATCHER_SAFETY_INTERVAL_SECONDS`, and
  `DISPATCHER_LISTEN_BACKOFF_SECONDS` to tune the warm-path dispatcher.
- `EVENT_RETENTION_DAYS` — single retention knob applied to every event table
  (`audit_events` and `file_events` today; `maintenance_events` once it lands).
  Per-table retention can be split out later if it becomes necessary.
- Storage maintenance knobs such as `STORAGE_MAINTENANCE_PURGE_BATCH`,
  `STORAGE_MAINTENANCE_MIGRATE_BATCH`, and
  `STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO`.

## Product Status

Relic is an early product implementation with substantial core behavior in
place. The web app, JSON API, metadata extraction, storage placement, the
event-driven warm-path dispatcher, and object gateway paths are actively
developed. Health endpoints are still placeholders, the
`maintenance_events` log is tracked in `ROADMAP.md`, and full S3
bucket/listing compatibility is not complete yet.
