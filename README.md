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

### Integrating as a service

Relic separates **metadata** (`/api/*`) from **bytes** (`/s3/*`). Every
`GET /api/files/{id}` response includes a `gateway` object:

```json
{
  "gateway": {
    "bucket": "photos",
    "key": "2024/cat.jpg",
    "object_uri": "/s3/photos/2024/cat.jpg"
  }
}
```

**Bucket/key mapping:** `gateway.bucket` is the first segment of the containing
folder's `path`; `gateway.key` is the remaining path segments plus the file name.
For a file directly under a top-level folder, the key is just the filename.

**Authentication:** Use one access key in two forms:

| Surface | Auth |
|---------|------|
| `/api/*` | `Authorization: Bearer {key_id}:{secret}` |
| `/s3/*` | AWS SigV4 `Authorization` header (same credentials, region `relic`, path-style) |

Do not send Bearer tokens to the S3 gateway — use SigV4 or presigned URLs.

**Reading bytes:** Either presign (`POST /api/uploads/presign-download`) or
issue a native SigV4 GET against `gateway.object_uri`. `blob_id` is for internal
deduplication only; it is not an object store address.

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

The Docker Compose stack below is **local development only**. Production runs
the three application images on Kubernetes — see
[Production Deployment (Kubernetes)](#production-deployment-kubernetes).

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

## Production Deployment (Kubernetes)

This section is for the infra team deploying Relic into an existing cluster.
Postgres, Redis, and S3-compatible object storage (Garage, MinIO, AWS S3, etc.)
are **external** — Relic only ships three application workloads plus a
one-off migration job.

### Container images

CI builds and pushes multi-platform (`linux/amd64`, `linux/arm64`) images on
every push to `main` and on version tags (`v*`):

| Image | Context | Default command |
|-------|---------|-----------------|
| `ghcr.io/<owner>/<repo>/relic-server` | `server/` | `uvicorn api.app:app --host 0.0.0.0 --port 8000` |
| `ghcr.io/<owner>/<repo>/relic-client` | `client/` | nginx on port 80 |

The **server image** serves both the API Deployment and the maintenance worker.
Only the container command differs.

Registry authentication uses the GitHub Actions `GITHUB_TOKEN` with `packages:
write`. For a private registry outside GHCR, mirror these images or retarget the
workflow. Clusters pulling from GHCR need a pull secret if the package is
private (`kubectl create secret docker-registry …`).

### Workloads

| Workload | Type | Replicas | Notes |
|----------|------|----------|-------|
| **api** | Deployment | ≥ 1 | HTTP on port **8000** |
| **worker-maintenance** | Deployment | **1** | Do not scale — cron enqueues jobs every minute; multiple replicas duplicate work |
| **client** | Deployment | ≥ 1 | Static SPA + nginx reverse proxy on port **80** |
| **migrate** | Job (one-off) | — | Run before first deploy and on every upgrade |

#### API container

- **Image:** server image (default CMD).
- **Port:** 8000.
- **Probes:**
  - Liveness: `GET /healthz` — process is up.
  - Readiness: `GET /readyz` — DB, Redis, registered storage-backend probe state, optional worker heartbeat. Returns **503** until storage backends are probed (maintenance worker must be running; first probe within ~1 minute of deploy).
- **Metrics:** `GET /metrics` (Prometheus text format, **not** under `/api`). Scrape port 8000 from the pod or via your ingress policy. Exposes API/gateway traffic, dependency readiness (`relic_dependency_up`), worker heartbeat age, DB pool stats, Redis command latency, auth attempts, and process metrics.

#### Maintenance worker container

- **Image:** server image.
- **Command:** `arq workers.maintenance.WorkerSettings`
- **Port:** **9100** — Prometheus metrics (`METRICS_WORKER_PORT`, disable with `METRICS_WORKER_ENABLED=false`). Scrape separately from the API; this is where maintenance job counters, queue depth, storage probes, and business gauges (`relic_files_total`, `relic_blobs_total`, `relic_storage_bytes`) are updated.
- **Cron:** enqueues seven jobs every minute (blob purge, storage-backend probes, tier demotion/promotion, audit/filesystem event retention trim, stale multipart abort).
- **Heartbeat:** writes `relic:heartbeat:maintenance` in Redis. Set `MAINTENANCE_HEARTBEAT_REQUIRED=true` on the API so `/readyz` fails when the worker is absent or stale.

#### Client container

- **Image:** client image.
- **Port:** 80.
- **Routing:** the bundled `nginx.conf` serves the SPA and reverse-proxies:
  - `/api/` → `http://api:8000/api/`
  - `/s3/` → `http://api:8000/s3/` (buffering disabled for large uploads)
- The upstream hostname is hardcoded as **`api`**. Name the Kubernetes Service
  for the API workload `api`, or replace `nginx.conf` via ConfigMap.
- Alternative: skip client-side proxying and terminate `/api` + `/s3` on a
  shared Ingress, serving the SPA from `/` only. The SPA defaults to
  `VITE_API_BASE_URL=/api` (same-origin); no build-time env is required when
  API and UI share an origin.

#### Migration job

Run before the first deploy and before restarting the API on every schema
upgrade:

```text
python seed.py
```

This runs `alembic upgrade head` then idempotent seeding (root folder, optional
seed folder, admin user if missing). Safe to re-run — it does not rotate an
existing admin password.

Wire the same env vars and secrets as the API/worker. The job needs Postgres
connectivity only (no Redis required for migrations).

See [docs/database-migrations.md](docs/database-migrations.md) for squashed-history
cutover, production sequencing, and local Alembic workflows.

### External dependencies

Relic expects these services to already exist in the cluster or network:

| Dependency | Used by | Purpose |
|------------|---------|---------|
| **PostgreSQL** | API, worker, migrate job | All relational state |
| **Redis** | API, worker | ARQ maintenance queue, tiered cache, worker heartbeats |
| **S3-compatible storage** | API, worker | Blob bytes — **registered at runtime** via admin UI, not configured purely by env |

Storage backends (bucket endpoint, credentials, tier) are created in the Relic
admin UI after deploy. Until at least one backend is registered and probed,
`/readyz` object-store check passes vacuously (zero backends = healthy). Plan to
register backends immediately after first deploy.

If using Relic's **embedded filesystem storage backend** (local disk instead of
remote S3), mount a PVC at `STORAGE_FILESYSTEM_BASE_PATH` on API and worker
pods. Both must share the same path if tiering moves blobs between backends on
disk.

### Networking summary

| Path | Handler | Auth |
|------|---------|------|
| `/api/*` | FastAPI JSON control plane | Session cookie or bearer access key |
| `/s3/*` | S3-compatible gateway | SigV4 (access key or presigned URL) |
| `/healthz` | Liveness | None |
| `/readyz` | Readiness | None |
| `/metrics` | Prometheus | None — restrict at network layer |
| `/docs`, `/redoc` | OpenAPI | None — disable or restrict in prod if desired |

Set `SESSION_COOKIE_SECURE=true` when the UI is served over HTTPS.

Set `S3_CORS_ALLOWED_ORIGINS` to the browser origin if uploads/downloads go
directly to `/s3` cross-origin (comma-separated list). Empty disables S3 CORS
middleware.

### Environment variables

All configuration is via environment variables (see `server/settings.py`). Grouped
by concern:

#### Required secrets (production)

Generate unique values — defaults are dev-only and `/readyz` reports warnings
but does not fail on them.

| Variable | Purpose |
|----------|---------|
| `ENCRYPTION_SECRET` | Fernet key for encrypted storage-backend credentials and access-key secrets at rest |
| `SESSION_SECRET` | HMAC key for session cookies — use a **separate** value from `ENCRYPTION_SECRET` |
| `RELIC_SIGNING_KEYS` | JSON map of `{ "key_id": "secret" }` for presigned S3 URLs |
| `RELIC_SIGNING_CURRENT_KEY_ID` | Active key id; must exist in `RELIC_SIGNING_KEYS` |
| `POSTGRES_PASSWORD` or `DATABASE_URL` | Database credentials |
| `REDIS_PASSWORD` | Redis AUTH |

Optional convenience: set `DATABASE_URL` (`postgresql+psycopg://…`) instead of
individual `POSTGRES_*` fields.

#### Database

| Variable | Default | Notes |
|----------|---------|-------|
| `POSTGRES_HOST` | `localhost` | |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_DB` | `relic` | |
| `POSTGRES_USER` | `relic` | |
| `POSTGRES_PASSWORD` | `relic` | |
| `DATABASE_URL` | — | Overrides `POSTGRES_*` when set |

#### Redis

| Variable | Default | Notes |
|----------|---------|-------|
| `REDIS_HOST` | `localhost` | |
| `REDIS_PORT` | `6379` | |
| `REDIS_PASSWORD` | `replace_me` | |
| `MAINTENANCE_QUEUE_NAME` | `relic:maintenance` | ARQ queue name |

Redis keys are prefixed `relic:` (cache generations, heartbeats, etc.). API
replicas require a **shared** Redis instance for cache invalidation coherence.

#### Sessions and seed data

| Variable | Default | Notes |
|----------|---------|-------|
| `SESSION_COOKIE_NAME` | `relic_session` | |
| `SESSION_MAX_AGE_SECONDS` | `604800` (7 days) | |
| `SESSION_COOKIE_SECURE` | `false` | Set `true` behind TLS |
| `RELIC_ADMIN_NAME` | `Relic Admin` | Used only when seeding a new admin |
| `RELIC_ADMIN_EMAIL` | `admin@relic.local` | |
| `RELIC_ADMIN_PASSWORD` | `relic-admin` | Only applied on **first** admin creation |
| `RELIC_SEED_FOLDER_NAME` | `Uploads` | Optional top-level folder; empty skips |

#### S3 gateway

| Variable | Default | Notes |
|----------|---------|-------|
| `RELIC_SIGNING_TTL_SECONDS` | `300` | Presigned URL lifetime |
| `RELIC_SIGNING_REGION` | `relic` | Native SigV4 clients must use this region |
| `RELIC_SIGNING_KEY_ID` | `relic-dev` | Fallback when `RELIC_SIGNING_KEYS` unset |
| `RELIC_SIGNING_SECRET` | derived | Fallback when `RELIC_SIGNING_KEYS` unset |
| `S3_CORS_ALLOWED_ORIGINS` | empty | Comma-separated browser origins |
| `MAX_OBJECT_BYTES` | `5368709120` (5 GiB) | Upload size cap |
| `UPLOAD_SPOOL_MAX_MEMORY_BYTES` | `8388608` | In-memory spool before disk |
| `S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS` | `24` | Stale multipart cleanup |

#### Worker and maintenance

| Variable | Default | Notes |
|----------|---------|-------|
| `MAINTENANCE_HEARTBEAT_REQUIRED` | `false` | Set **`true`** in production |
| `MAINTENANCE_HEARTBEAT_TTL_SECONDS` | `180` | |
| `MAINTENANCE_HEARTBEAT_STALE_SECONDS` | `120` | |
| `EVENT_RETENTION_DAYS` | `90` | Audit + filesystem event trim |
| `PROBES_RETENTION_DAYS` | `14` | Storage-backend probe history |
| `STORAGE_MAINTENANCE_PURGE_BATCH` | `80` | Dereferenced blob purge batch |
| `STORAGE_DEMOTION_PRESSURE_RATIO` | `0.85` | Tier demotion threshold |
| `STORAGE_PROMOTION_HEADROOM_RATIO` | `0.70` | Tier promotion threshold |
| `STORAGE_PROMOTION_RECENCY_DAYS` | `7` | |
| `STORAGE_MIGRATION_MIN_RESIDENCY_HOURS` | `6` | Anti-ping-pong after migration |
| `STORAGE_WRITE_HEADROOM_RATIO` | `0.95` | Placement headroom on upload |
| `STORAGE_DEMOTE_BATCH` | `24` | |
| `STORAGE_PROMOTE_BATCH` | `24` | |
| `PLACEMENT_REQUIRE_REACHABLE_STORAGE_BACKEND` | `true` | Skip unprobed backends for new writes |
| `PROBE_RANKING_WINDOW` | `3` | Probe samples for hotness ranking |

#### Caching and logging

| Variable | Default | Notes |
|----------|---------|-------|
| `FOLDER_METADATA_CACHE_TTL_SECONDS` | `120` | |
| `S3_LIST_OBJECTS_CACHE_TTL_SECONDS` | `15` | |
| `S3_ACCESS_KEY_CACHE_TTL_SECONDS` | `120` | |
| `S3_ACCESS_KEY_LAST_USED_DEBOUNCE_SECONDS` | `60` | |
| `ACCESS_TOUCH_DEBOUNCE_MINUTES` | `5` | Blob `accessed_at` debounce |
| `LOG_LEVEL` | `INFO` | JSON logs to stdout |
| `STORAGE_FILESYSTEM_BASE_PATH` | — | Root for embedded filesystem backends |

Server and worker Deployments should receive the **same** env var set (except
nothing worker-specific today — share a ConfigMap/Secret).

### Deploy and upgrade order

**First deploy**

1. Run **migrate** Job (`python seed.py`).
2. Start **worker-maintenance** (single replica).
3. Start **api**.
4. Start **client** (or your Ingress equivalent).
5. Log in as admin; register storage backends in the admin UI.
6. Wait for maintenance probe tick; confirm `/readyz` is 200.
7. Change the seeded admin password if this is a fresh install.

**Upgrades**

1. Backup Postgres.
2. Run **migrate** Job with the new server image tag.
3. Roll **worker-maintenance**, then **api**, then **client**.

### Scaling notes

- **API:** horizontal scaling is supported. All replicas share Postgres + Redis.
  Redis outage degrades cross-replica cache invalidation (permissions/listings may
  lag until TTL expiry).
- **Worker:** keep at **one** replica.
- **Client:** stateless; scale freely.

### Observability

- Logs: structured JSON on stdout (`structlog`). No separate log shipper in-repo.
- Metrics: scrape `http://<api-pod>:8000/metrics`. Key series include
  `relic_api_requests_total`, `relic_gateway_requests_total`,
  `relic_maintenance_jobs_total`, `relic_maintenance_queue_depth`,
  `relic_storage_backend_probe_total`.
- Readiness JSON includes per-check detail (DB, Redis queue depth, unhealthy
  storage backends, worker heartbeat age, configuration warnings).

### Integrator note (filesystem events)

Downstream services poll `GET /api/filesystem-events` with bearer access keys
granted **READ** on watched folders. Metadata enrichment uses
`PATCH /api/files/{id}/meta` (**ENRICH** permission). Delivery is pull-only (seq
cursor); see `events.md` for event types, retention, and ACL rules.

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

Environment variables are documented in the
[Production Deployment (Kubernetes)](#production-deployment-kubernetes) section
(`server/settings.py` is the source of truth). For local development, see
`docker-compose.yaml` and the variables listed there.

Key groups: Postgres (`POSTGRES_*` or `DATABASE_URL`), Redis (`REDIS_*`),
encryption/session secrets, S3 signing keys (`RELIC_SIGNING_*`), maintenance
tuning, and retention (`EVENT_RETENTION_DAYS`).

## Product Status

Relic is an early product with substantial core behavior in place. The web
app, JSON API, object gateway, native SigV4 clients, content-hash
deduplication, tiered storage placement, unified `audit_events`, Prometheus
`/metrics`, and production health / readiness endpoints are live. Planned work
includes external activity sinks, import-from-bucket flows, quotas, extended
retention controls, versioning, and richer admin file/blob inspection.
