# Relic Architecture Manifest

This document is the north star for the Relic server backend architecture. It
captures layer boundaries, extensibility goals, and how the gateway vs control
plane split is organized in code.

It complements [api-split.md](./api-split.md), which defines the **gateway vs
control plane** operation matrix.

---

## Goals

1. **Clear boundaries** — domain rules, orchestration, persistence, and I/O are
   separate; no god modules.
2. **Gateway vs control plane** — two protocol surfaces share one application
   core, not duplicate business logic.
3. **Dual API for file operations** — file operations should be available via
   both the S3 gateway and the traditional Relic JSON HTTP API (see
   [Dual protocol surfaces](#dual-protocol-surfaces-for-file-operations)).
4. **Swappable metadata DB** — Postgres in production; SQLite for tests and
   optional embedded mode; other relational backends via adapters when needed.
5. **Swappable object storage per bucket** — S3-compatible remote stores,
   local NVMe filesystem for hot caching near users, in-memory for tests.
6. **Thin entry points** — HTTP routes and workers translate protocols; they do
   not own transactions or encode business rules.
7. **Vertical rewrite** — migrate slice by slice; the app stays runnable after
   each slice.

---

## Layer Layout (Implemented)

```
server/
  domain/                 # Pure rules (naming, meta, paths, permissions, search matching)
  application/            # Use cases and orchestration (UoW in, no direct commits)
    control_plane/        # Relic JSON API semantics
    gateway/              # S3 mutation façade (object_mutations, delete_object, signing shims)
    maintenance/          # Retention orchestration (audit trim, multipart abort)
  ports/                    # Protocols (repositories, storage, cache, context)
    repositories/         # FileStore, PermissionStore, SearchStore, …
    context.py            # Actor, EventContext
  infra/                    # SQLAlchemy, boto3, SigV4, caches
    db/
      models.py           # ORM
      stores/             # folder_access, placement, access_keys, audit_events, …
      repositories/       # Store implementations
    gateway/              # Session-level S3 I/O (writes, listing, multipart, paths)
    maintenance/          # Blob purge, rebalance, probe cron jobs
    auth/                 # SigV4 (s3_signing)
    object_storage/       # S3, filesystem, memory adapters + registry
    auth/s3_signing.py    # SigV4 verify/sign
    cache/                # list-objects + folder tree hot-path caches
  api/                      # Thin HTTP entry points
  workers/                  # ARQ cron jobs → run_with_uow
  composition.py            # build_uow()
```

Entry points import **`application.*` use cases**. Persistence and I/O live in
**`infra/`**. The old `server/services/` directory has been removed. Dead
`processors/` tree removed.

---

## Historical Note: Pre-Rewrite Problems

The section below describes why the rewrite was needed. These issues are resolved
in the layout above.

## Current Problems (Why Rewrite)

> **Status:** The flat `server/services/` layer has been removed. The layout in
> [Layer Layout](#layer-layout-implemented) is in place.

### Historical pains (resolved)

Modules once sliced the problem on inconsistent axes (Relic domain vs S3 protocol
vs infrastructure). **`services/` is deleted**; bounded contexts live under
`application/` with ports in `ports/` and adapters in `infra/`.

### Rewrite completion checklist

| Area | Status |
| --- | --- |
| `services/` removed | **Done** |
| Composition + `UnitOfWork` | **Done** — `UnitOfWorkDep` / `run_with_uow` |
| Control-plane file ops on UoW | **Done** — move/rename/patch/bulk |
| Gateway mutations on UoW | **Done** — `object_mutations` + `delete_object` |
| Unified file delete | **Done** — `remove_file_record` (HTTP + S3 gateway) |
| `folder_access` in infra | **Done** — `infra/db/stores/folder_access.py` + `infra/cache/folder_access.py` |
| `SearchStore` dialect split | **Done** — Postgres vs portable |
| `StorageRegistry` per bucket | **Done** — S3 + filesystem + `StorageKind` |
| `StorageCapabilities` enforced | **Done** — `ports/storage_policy.py`; put + multipart in `infra/gateway` |
| Maintenance on UoW | **Done** — purge/probe/rebalance/migrate |
| SigV4 in infra | **Done** — `infra/auth/s3_signing.py` |
| Tests via Alembic | **Done** — `tests/db.py` + shared `conftest.py` |
| Dual API file delete | **Done** — `DELETE /api/files/{id}` + S3 `DeleteObject` share removal use case |
| Dual API file bytes | **By design** — gateway bytes + `/api/uploads` presign to gateway URLs |
| Application fake-store tests | **Done** — `test_remove_file`, `test_gateway_put_object`, `test_storage_policy` |
| Read routes via application | **Done** — `browse_filesystem`, `list_folder_access`, `s3_listing`, `session_auth`, `presigned_access` |
| API imports application for orchestration | **Done** — routes call `application.*`; infra only for XML/helpers |
| No `infra.db.models` in `application/` | **Done** — use `ports.entities` |
| Infra stores defer commit to UoW | **Done** — no `commit=` on folder_access / audit / access_keys |
| Gateway session I/O in infra | **Done** — `infra/gateway/*`; `application/gateway/` façade + signing re-export |
| `UnitOfWork` protocol in `ports/uow.py` | **Done** |

### Original pain points (for context)

#### Inconsistent organization

| Axis | Examples |
| --- | --- |
| Relic domain | `files`, `folders`, `filesystem`, `folder_access`, `users`, `buckets` |
| S3 / protocol layer | `objects`, `s3_listing`, `s3_multipart`, `s3_signing`, `s3_hotpath_cache` |
| Infrastructure | `placement`, `event_context`, `health`, `storage_maintenance` |

A single “file” operation may touch `files`, `objects`, `folder_access`,
`placement`, and `s3_hotpath_cache`. There is no obvious home for new work.

### God modules

- **`folder_access.py`** — ACL admin, authorization checks, folder tree
  materialization, and module-level TTL caches in one file. Imported by most
  other services.
- **`objects.py`** — *(removed)* was S3 gateway semantics, blob lifecycle, path
  resolution, and boto3 I/O in one file. Split into `object_writes`, `object_reads`,
  `object_paths`, etc.

### Persistence is inlined everywhere

Service functions take a raw SQLAlchemy `Session`, run queries inline, and call
`db.commit()` scattered across modules. There is no repository port, unit-of-work
boundary, or composition root. Swapping Postgres for SQLite — or any other
metadata backend — means rewriting large parts of `services/`, not flipping
configuration.

### Schema and tests diverge

Production uses Alembic migrations (Postgres-first; some steps use raw JSONB SQL
and GIN indexes). Tests use in-memory SQLite with `Base.metadata.create_all()`,
 bypassing migrations. Test schema and prod schema can drift.

### Backend is bigger than the RDBMS

Relic also hard-depends on Redis + ARQ (maintenance workers) and S3-compatible
object storage. True portability requires ports for each, not just the database.

---

## Target Architecture

Relic is **one product with three entry surfaces** that call the **same
application core**:

```
                    ┌─────────────────┐
                    │  Control plane  │  Relic JSON API (UI, admin)
                    └────────┬────────┘
                             │
┌─────────────────┐          │          ┌─────────────────┐
│   S3 gateway    │──────────┼──────────│  ARQ workers    │
│  (DuckLake…)    │          │          │  (maintenance)  │
└────────┬────────┘          │          └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
                    ┌─────────────────┐
                    │   Application   │  Use cases / commands
                    │   (orchestrate) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Domain  │  │  Ports   │  │  Infra   │
        │  (pure)  │  │(abstract)│  │(concrete)│
        └──────────┘  └──────────┘  └──────────┘
```

**Rule:** nothing above `infra/` imports SQLAlchemy, boto3, or Redis clients
except adapter implementations and the composition root.

See [api-split.md](./api-split.md) for which operations belong on the gateway
vs control plane. When adding features, use this decision rule:

- Does it move bytes? → Gateway.
- Does S3 have a verb that's a clean fit and an external client will use it? →
  Gateway.
- Otherwise → Control plane.

### Dual protocol surfaces for file operations

**File operations should be available via both the S3 gateway and the more
traditional HTTP API** (Relic JSON control plane under `/api/…`).

Users, the UI, DuckLake, rclone, and other S3 clients must be able to perform
the same fundamental file work through whichever surface fits their integration —
without divergent behavior or duplicate business logic. Both surfaces call the
**same application use cases**; only the protocol translation differs (S3 XML +
SigV4 vs JSON + session cookies / bearer auth).

| Concern | S3 gateway | Traditional HTTP API |
| --- | --- | --- |
| Primary consumers | DuckLake, rclone, S3 SDKs | Relic UI, scripts, admin tools |
| Auth | SigV4 / access keys | Session / admin API |
| Response shape | S3 XML / headers | Rich JSON (`File`, errors, bulk results) |
| Strength | Bytes, streaming, compatibility | Bulk ops, structured errors, metadata CRUD |

Operations may land primarily on one surface first (see [api-split.md](./api-split.md)),
but the rewrite target is **capability parity where it makes sense**: upload,
download, delete, copy, list, and metadata-oriented file work should remain
reachable from both paths over time, implemented once in `application/` and
exposed twice at the edges (`api/s3_gateway.py` and `api/files.py`).

Example: deleting a file via `DELETE` on the gateway and via a control-plane
endpoint should run the same `delete_object` / file-removal use case; moving or
renaming may be control-plane-first but must not preclude a future S3-shaped
equivalent if compatibility demands it.

---

## Layers

### 1. Domain (`server/domain/`)

Pure logic — no I/O, no `Session`, no HTTP, no side effects.

**Belongs here:**

- Naming and validation rules (filenames, folder names)
- Permission bitmask rules
- Path derivation (given a folder graph, compute paths)
- Blob attribute sniffing (`domain/blobs/sniff.py` today)
- File meta normalization (`domain/files/meta.py` today)
- Placement ranking math (given probe samples, rank buckets)
- Audit event shape validation (operation names, status values)
- Search filter matching logic (when SQL cannot express predicates portably)

**Properties:**

- Fully unit-testable without a database.
- Expand this layer until most of `folder_access` path logic and `search`
  filter matching live here.

### 2. Application (`server/application/`)

Use cases / orchestration. Replaces the conceptual role of `server/services/`.

```
server/application/
  context.py              # Actor, RequestContext (replaces event_context.py)
  uow.py                  # UnitOfWork protocol

  control_plane/          # Relic JSON API semantics
    move_file.py
    create_folder.py
    search_files.py
    grant_folder_access.py
    ...

  gateway/                # S3-shaped operations
    put_object.py
    get_object.py
    list_objects_v2.py
    complete_multipart.py
    verify_signature.py

  maintenance/            # Background jobs
    purge_blobs.py
    probe_buckets.py
    rebalance_blobs.py
    migrate_blob.py       # cross-backend blob moves
```

Each use case exposes one primary function:

```python
def move_file(
    uow: UnitOfWork,
    *,
    actor: Actor,
    file_id: UUID,
    destination_folder_id: UUID,
    name: str | None,
) -> FileView:
    ...
```

**Properties:**

- Receives a `UnitOfWork`; does not open connections.
- Commits once via the UoW (or the route/worker owns commit).
- Emits audit records through `AuditSink`, not inline DB calls.
- Invalidates cache through `CachePort`, not module-global dicts.
- Gateway and control-plane use cases **share stores**; gateway use cases also
  call `ObjectStorage`.

### 3. Ports (`server/ports/`)

Protocols for what the application needs from the outside world.

```
server/ports/
  stores/
    files.py
    folders.py
    folder_access.py    # split ACL admin from permission checks
    blobs.py
    buckets.py
    users.py
    access_keys.py
    audit.py
    multipart.py
    search.py           # primary dialect seam for metadata

  object_storage.py     # put / get / head / delete / copy / multipart
  storage_registry.py   # resolve bucket → ObjectStorage adapter
  cache.py
  clock.py
  crypto.py             # secret encryption (wraps utils/crypto)
  queue.py              # optional job enqueue (ARQ)
```

Example store interface:

```python
class FileStore(Protocol):
    def get(self, file_id: UUID) -> File | None: ...
    def get_by_folder_and_name(self, folder_id: UUID, name: str) -> File | None: ...
    def save(self, file: File) -> None: ...
    def delete(self, file_id: UUID) -> None: ...
```

### 4. Infrastructure (`server/infra/`)

Concrete adapters. All messy I/O lives here.

```
server/infra/
  db/
    engine.py
    uow_sqlalchemy.py
    models/               # ORM models (move from top-level models.py)
    stores/
      sqlalchemy_files.py
      sqlalchemy_folders.py
      sqlalchemy_search_postgres.py
      sqlalchemy_search_sqlite.py
      ...

  object_storage/
    s3.py
    filesystem.py
    memory.py
    registry.py           # BucketKind → ObjectStorage factory

  cache/
    request_scoped.py     # replaces s3_hotpath_cache + folder_access caches
    redis.py              # optional shared cache (multi-instance)

  auth/
    sessions.py
    s3_signing.py           # SigV4 verify/sign

  queue/
    arq.py

  audit/
    sqlalchemy_sink.py
```

### 5. Entry points (thin)

```
server/api/           # HTTP: parse, auth, call use case, serialize
server/workers/       # Cron: open UoW, call maintenance use case
server/composition.py # Wiring: builds UoW from settings
```

Routes import `application.*`. FastAPI dependencies yield a `UnitOfWork` for
mutating file operations.

```python
def get_uow() -> Generator[UnitOfWork, None, None]:
    uow = build_uow(settings)
    try:
        yield uow
        uow.commit()
    except Exception:
        uow.rollback()
        raise
    finally:
        uow.close()
```

---

## Unit of Work (Keystone)

One transaction boundary per HTTP request or worker job.

```python
class UnitOfWork(Protocol):
    files: FileStore
    folders: FolderStore
    permissions: PermissionStore
    blobs: BlobStore
    buckets: BucketStore
    search: SearchStore
    multipart: MultipartStore
    audit: AuditSink
    cache: CachePort
    storage: StorageRegistry

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...
```

Use cases orchestrate across stores. Individual functions do not call
`db.commit()`. Audit events flush in the same transaction where possible.
Workers use the same UoW — maintenance is not a separate persistence style.

---

## Bounded Contexts

Organize application modules by how Relic thinks, not how S3 thinks.

| Context | Application | Stores / ports | Notes |
| --- | --- | --- | --- |
| **Identity** | users, access_keys, auth | UserStore, AccessKeyStore | Admin control plane |
| **Filesystem** | folders, files, browse, stats | FolderStore, FileStore, PermissionStore | Relic-native |
| **Gateway objects** | put/get/delete/copy/list/multipart | + ObjectStorage, MultipartStore | S3-shaped |
| **Blob storage** | (internal) | BlobStore, BucketStore | Refcount, dedup, placement |
| **Search** | search_files, facets | SearchStore | Dialect-specific impls |
| **Audit** | (cross-cutting) | AuditSink | Every use case logs here |
| **Maintenance** | purge, probe, rebalance, migrate | BlobStore + ObjectStorage | Workers only |

### Mapping from current `services/` modules

| Today | Target home |
| --- | --- |
| `folder_access.py` | `infra/db/stores/folder_access.py` + `infra/cache/folder_access.py` + `PermissionStore` |
| `placement.py` | `infra/db/stores/placement.py` + `domain/storage/hotness.py` |
| `access_keys.py` | `infra/db/stores/access_keys.py` + `AccessKeyStore` |
| `s3_signing.py` | `infra/auth/s3_signing.py` |
| `event_context.py` | `ports/context.py` + `application/context.py` (Actor.from_user) |
| `objects.py` | `application/gateway/*` + `BlobStore` + `ObjectStorage` |
| `files.py`, `filesystem.py`, `folders.py` | `application/control_plane/*` + stores |
| `s3_listing.py`, `s3_multipart.py` | `application/gateway/object_listing.py`, `object_multipart.py` |
| `s3_hotpath_cache.py` | `infra/cache/hotpath.py`, `infra/cache/list_objects.py` |
| `storage_maintenance.py` | `application/maintenance/storage.py`, `retention.py` |
| `search.py` | `application/control_plane/search_files.py` + `SearchStore` |
| `health.py` | `application/health.py` |

**Completed:** `services/` deleted. Business logic lives in `application/`; SQLAlchemy
store implementations in `infra/db/repositories/`.

---

## Metadata Database Portability

Metadata (users, folders, files, ACLs, audit, multipart state, bucket registry)
and object bytes are **separate concerns** with separate port families.

### Supported target

Commit to a **portable relational core** with **dialect-enhanced fast paths**:

| Backend | Role | Notes |
| --- | --- | --- |
| **PostgreSQL** | Production default | JSONB, GIN indexes, `SKIP LOCKED`, partial unique indexes |
| **SQLite** | Tests, embedded / single-user dev | Python-side JSON filters; no GIN |
| **CockroachDB / Yugabyte** | Optional | Often Postgres wire-compatible; probe locking quirks |
| **MySQL / MariaDB** | Opt-in adapter | JSON operators differ; search needs new strategy |

Not targeted: DynamoDB-style metadata, “any JDBC database,” ORM-agnostic raw SQL
in use cases.

### Capability matrix

Dialect differences are centralized — not scattered `if dialect` in use cases.

```python
@dataclass(frozen=True)
class DbCapabilities:
    dialect: str
    json_path_queries: bool       # meta->>'mimetype'
    json_contains: bool           # @>, ?|  (Postgres JSONB)
    partial_unique_indexes: bool
    skip_locked: bool
    advisory_locks: bool
```

Use cases call `SearchStore.search(query)`. Adapters choose strategy:

- **Postgres** — GIN indexes + native JSONB predicates (see migration
  `0004_file_meta_search_indexes`; Postgres-only, skipped on SQLite).
- **SQLite** — SQL pre-filter on portable columns, JSON predicates in Python
  (current `search.py` approach).
- **Other SQL** — implement adapter or fall back to portable + Python.

### Configuration

Single engine factory driven by environment:

```yaml
database:
  url: postgresql+psycopg://...   # or sqlite:///relic.db
```

`server/composition.py` detects capabilities from the engine and wires the
matching store implementations.

### Schema truth

- ORM models live in `server/infra/db/models/` (persistence detail).
- Alembic remains the schema authority for all environments.
- Tests run migrations against SQLite (or a shared fixture DB), not only
  `Base.metadata.create_all()`, to prevent prod/test drift.
- Postgres-only migrations (GIN indexes, `jsonb_build_object` data migrations)
  stay explicit in Alembic with dialect guards.

---

## Object Storage Portability

### ObjectStorage port

```python
class ObjectStorage(Protocol):
    def put(self, *, bucket: str, key: str, body: BinaryIO, size: int) -> PutResult: ...
    def get(self, *, bucket: str, key: str, range: Range | None = None) -> GetResult: ...
    def head(self, *, bucket: str, key: str) -> HeadResult: ...
    def delete(self, *, bucket: str, key: str) -> DeleteResult: ...
    def copy(self, *, src_bucket, src_key, dest_bucket, dest_key) -> CopyResult: ...
    # multipart_* methods when supported
```

### Adapters

| Adapter | Role |
| --- | --- |
| `S3ObjectStorage` | Production remote stores (Garage, MinIO, AWS, …) |
| `FilesystemObjectStorage` | Local NVMe / disk; content keyed under `base_path/bucket/key` |
| `MemoryObjectStorage` | Unit and integration tests |
| `CompositeObjectStorage` | Optional router delegating by bucket name |

### Per-bucket adapter selection

Each **Bucket** row in the metadata DB is a registry entry, not implicitly S3:

```python
class StorageBackendKind(str, Enum):
    S3 = "s3"
    FILESYSTEM = "filesystem"
```

Fields include `kind`, connection config (S3 endpoint + credentials **or**
filesystem `base_path`), capacity limits, and probe configuration.

`BlobStore` records `(bucket_id, key, content_hash, refcount)`. When moving
bytes, the application resolves `ObjectStorage` via `StorageRegistry`:

```python
storage = uow.storage.for_bucket(blob.bucket_id)
storage.get(bucket=..., key=...)
```

**Placement** chooses which bucket (and therefore which adapter) receives new
uploads. **Maintenance rebalance** can migrate blobs between backends (e.g. hot
local NVMe → cold remote S3, or the reverse) by read-from-A / write-to-B /
update blob row / adjust refcount.

### Hot NVMe cache near users

Per-bucket adapter selection enables a **geographic / latency tiering** model:

```
┌──────────────┐     low latency      ┌─────────────────────┐
│ User /       │ ◄──────────────────► │ Hot bucket          │
│ DuckLake     │   presigned GET/PUT  │ (filesystem / NVMe) │
└──────────────┘                      └──────────┬──────────┘
                                                 │ rebalance / demote
                                                 ▼
                                      ┌─────────────────────┐
                                      │ Cold bucket           │
                                      │ (remote S3 / Garage)  │
                                      └─────────────────────┘
```

- **Hot bucket** — `FilesystemObjectStorage` on local NVMe close to the Relic
  gateway instance serving the user. Frequent reads and writes avoid round-trips
  to geographically distant S3.
- **Cold bucket** — remote S3-compatible store for durability and cost.
- **Demote / promote** — existing placement and maintenance cron logic extended
  to call `migrate_blob` across adapters when access patterns or capacity change.

Domain rules (refcount, content-hash dedup, folder paths) are unchanged; only
where bytes live differs.

### Storage capability matrix

Gateway and upload flows respect adapter limits in the **gateway application
layer**, not in domain rules:

```python
@dataclass(frozen=True)
class StorageCapabilities:
    multipart: bool
    ranged_reads: bool
    server_side_copy: bool
    list_prefix: bool
    presigned_urls: bool
    max_single_put_bytes: int | None
```

| Concern | S3 | Filesystem |
| --- | --- | --- |
| Multipart | Yes | Optional (chunk files or single write) |
| Range reads | Native | `seek` + read |
| Server-side copy | CopyObject | Reflink / hardlink / read+write |
| ETag | Often content MD5 | Content hash hex |
| Presigned URLs | Yes | Session-auth download or internal only |
| Listing | ListObjectsV2 | Directory walk (different perf) |

When `multipart=False`, gateway degrades gracefully (single PUT policy or size
limits). When `presigned_urls=False`, control plane may offer authenticated
download endpoints instead.

### S3 gateway vs filesystem backend

The **S3 gateway remains the compatibility surface** for DuckLake, rclone, and
similar clients. Filesystem storage replaces **where bytes are stored behind**
`PutObject` / `GetObject` — it does not replace SigV4 or S3 XML responses.

```
S3 client ──► S3 gateway API ──► put_object use case ──► ObjectStorage adapter
                                                              ├── S3 (remote)
                                                              └── Filesystem (NVMe)
```

A non-S3 upload API would be a separate, optional product mode and is out of
scope unless explicitly chosen.

### Example configuration

```yaml
storage:
  default_backend: hot

  backends:
    hot:
      kind: filesystem
      base_path: /var/relic/hot
    cold:
      kind: s3
      endpoint: https://garage.example
      bucket: relic-cold
      region: garagem
      credentials: ...
```

Bucket rows in the DB mirror or are admin-created via the control plane; the port
interface is the same either way.

---

## Deployment Modes

| Mode | Metadata DB | Object storage | Queue | Use case |
| --- | --- | --- | --- | --- |
| **Production** | PostgreSQL | S3 fleet + optional hot FS buckets | Redis + ARQ | Multi-user, multi-region |
| **Embedded / demo** | SQLite file | Local filesystem | Inline or optional Redis | Single-node, air-gapped |
| **CI / tests** | SQLite memory | Memory or temp directory | Inline | Fast, deterministic |

---

## Caching

Replace module-level globals (`_FOLDER_TREE_CACHE`, `s3_hotpath_cache`, placement
usage cache) with a **`CachePort`**:

- **Request-scoped** — per-request dict for S3 ListObjects hot path.
- **Process TTL** — folder tree rows, effective permissions.
- **Redis (optional)** — shared invalidation for multi-instance deployments.

Use cases call `cache.invalidate("folder_tree")` after mutations. Cache policy
lives in `infra/cache/`, not in domain or ACL modules.

---

## Testing Pyramid

| Layer | Approach |
| --- | --- |
| `domain/` | Pure unit tests, no DB |
| `application/` | Use case tests with **in-memory fake stores** |
| `infra/stores/` | Integration tests against SQLite (+ Postgres in CI matrix) |
| `infra/object_storage/` | Memory and temp-filesystem adapters |
| `api/` | HTTP tests via composition root; one shared `conftest.py` |

Eliminate duplicated per-file SQLite fixtures; one `build_uow(test_settings)`.

---

## Rewrite Sequence (Complete)

All slices below are implemented. New work should extend this layout, not reintroduce
`services/` or Session-committed use cases.

1. Composition + UoW + stores — **done**
2. Control-plane verticals (`move_file`, bulk ops, folders, users) — **done**
3. Gateway verticals (`object_mutations`, unified delete) — **done**
4. `folder_access` → infra stores + cache — **done**
5. `SearchStore` Postgres/SQLite — **done**
6. `StorageRegistry` + filesystem adapter — **done**
7. Maintenance on UoW + cross-backend blob migrate — **done**
8. Delete `services/` — **done**

---

## Target Repository Layout

```
server/
  domain/
  application/
    control_plane/
    gateway/
    maintenance/
    context.py
    uow.py
  ports/
  infra/
    db/
    object_storage/
    cache/
    auth/
    queue/
  api/
  workers/
  composition.py
  settings.py
  enums.py
  constants.py
  alembic/
  tests/
    unit/domain/
    unit/application/
    integration/stores/
    integration/object_storage/
    api/
```

Keep `utils/` for generic helpers only (logging, timing, passwords). Business
meaning belongs in `domain/` or `ports/`.

---

## Anti-Patterns (Do Not)

- **`BaseService` class hierarchies** — functions + protocols are enough.
- **Mirror every table** as domain entity + ORM model + DTO unless pain demands it.
- **Abstract everything preemptively** — implement ports when a second adapter exists
  or is imminent (Postgres/SQLite, S3/Filesystem).
- **S3 XML parsing in use cases** — stays in `api/s3_gateway.py` as protocol
  translation; use cases speak domain commands.
- **Dialect branches in use cases** — only in store adapters via capability flags.
- **Promising “any database + any blob store”** — architecture supports
  extensibility; product commits to a short supported list.
- **Re-export shortcuts** — no compatibility shims; refactor and document breaking
  changes.

---

## One-Sentence Summary

**Domain rules are pure; use cases orchestrate through a Unit of Work; file
operations are exposed via both the S3 gateway and the traditional HTTP API;
metadata stores and object storage are independent port families with capability
matrices; Postgres, SQLite, S3, local filesystem, Redis, and SigV4 are adapters
wired in `composition.py`; HTTP routes and workers are dumb translators.**

---

## Related Documents

- [api-split.md](./api-split.md) — gateway vs control plane operation matrix
- [.cursor/rules/backend.mdc](./.cursor/rules/backend.mdc) — coding conventions during migration
