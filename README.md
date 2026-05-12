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
- A worker parses files into a common metadata schema and runs storage
  maintenance jobs for cleanup, bucket probing, and lifecycle migration.

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

### Parsing

Uploaded and copied files are queued for asynchronous parsing. The parser
currently detects or enriches metadata for:

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

Parser output is merged with upload-time metadata while preserving user-provided
values where they overlap.

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

### Audit Log and Events

- Durable `events` table for audit records across the JSON API, S3 gateway, and
  background processors.
- Mutating operations write audit events in the same database transaction as the
  user, folder, file, bucket, access, object, or metadata mutation.
- Read-only access events such as S3 `GET` and `HEAD` are persisted
  synchronously before the request is considered complete.
- Event records capture source, operation, status, actor, request ID, related
  file/folder/blob IDs, and operation-specific metadata.
- Admin audit log UI with filters for source, operation, status, request ID,
  actor, and time range.
- Expandable event details that show metadata and related entity IDs for
  investigation.
- Parser failure events include processor stage, filename, MIME type when
  available, and exception class/message.
- Admin-only audit log clearing for local or operational reset workflows.

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

Relic is split into a React client, a FastAPI server, and an ARQ worker:

- `client/` is a Vite, React, TypeScript, Tailwind, and shadcn/ui app.
- `server/api/` contains the HTTP API and S3 gateway routes.
- `server/services/` contains the filesystem, object, bucket, search, access,
  placement, events, and maintenance logic.
- `server/parsers/` contains the metadata parser queue and toolchains.
- PostgreSQL stores users, folders, files, blobs, access grants, access keys,
  bucket registrations, and durable event records.
- Redis backs ARQ parser and maintenance jobs.
- Garage is used by the local Docker setup as two S3-compatible object stores,
  one hot and one cold.

## Local Development

The repository includes a Docker Compose stack for the full local product:

- PostgreSQL.
- Redis.
- API server.
- Parser and maintenance worker.
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

Run the worker manually:

```bash
cd server
uv run arq parsers.worker.WorkerSettings
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
- Parser byte caps such as `IMAGE_PARSE_MAX_BYTES`, `PDF_PARSE_MAX_BYTES`,
  `TEXT_PARSE_MAX_BYTES`, and related per-format limits.
- Storage maintenance knobs such as `STORAGE_MAINTENANCE_PURGE_BATCH`,
  `STORAGE_MAINTENANCE_MIGRATE_BATCH`, and
  `STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO`.

## Product Status

Relic is an early product implementation with substantial core behavior in
place. The web app, JSON API, metadata parsing, storage placement, and object
gateway paths are actively developed. Health endpoints are still placeholders,
and full S3 bucket/listing compatibility is not complete yet.
