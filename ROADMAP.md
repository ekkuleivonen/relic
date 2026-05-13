# Relic Roadmap

This roadmap captures the next product layers that would make Relic feel less
like a file manager and more like dependable storage infrastructure.

## Near Term

### Async Processors

The current single-queue parser/maintenance worker becomes a broader processor
system organized around three concurrency tiers:

- **Hot path** is the synchronous S3 gateway and REST API. It mutates canonical
  tables, emits events, and returns. It does not own any async work; it only
  produces the triggers other paths consume.
- **Warm path** is the `relic:processing` queue. It runs event-driven processor
  substrates (`meta_extract`, future `preview`, `thumbnail`, `text_extract`,
  `stats_rollup`, external sink delivery). Each warm job takes a `FileEvent` id
  and a processor name as input.
- **Cold path** is the `relic:maintenance` queue. It runs scheduled batches
  (purge dereferenced blobs, bucket probes, blob rebalance, event retention
  trim). It is invisible to external consumers.

The two queues run as separate worker pools so a slow rebalance batch can never
queue behind a fast metadata extraction (and vice versa).

#### Module reorganization

- `server/parsers/` becomes `server/processors/meta_extract/`. The metadata
  extractor is the first processor substrate; future substrates land as siblings
  under `server/processors/<substrate>/`.
- `server/parsers/worker.py` splits into `server/processors/worker_processing.py`
  (warm) and `server/processors/worker_maintenance.py` (cold). Each binds to
  exactly one queue.
- `server/services/parser_queue.py` becomes `server/services/processor_queue.py`
  with a thin enqueue helper per substrate.
- `PARSER_QUEUE_NAME` is retired. Two new env knobs replace it:
  `PROCESSING_QUEUE_NAME` (default `relic:processing`) and
  `MAINTENANCE_QUEUE_NAME` (default `relic:maintenance`).

#### Outbox dispatcher

Warm processors do not subscribe to API hooks. They subscribe to the
`file_events` outbox through a per-processor cursor stored on the `processors`
table (see Event Tables below). The dispatcher uses a pull model:

1. Listens on the Postgres `file_event_emitted` channel via `LISTEN/NOTIFY`
   as a wake-up signal. Also wakes every few seconds on a safety-net tick.
2. For each enabled `Processor` row, selects
   `file_events WHERE offset > processor.last_committed_offset AND event_type
   IN processor.subscribed_event_types ORDER BY offset ASC LIMIT BATCH_SIZE`.
3. Enqueues one `relic:processing` job per event with
   `_job_id = f"{processor_id}:{event_id}"`. arq's built-in `_job_id` dedup
   silently drops duplicates, so re-firing the same dispatcher tick is safe.
4. Does **not** advance the cursor on enqueue. The worker advances the cursor
   only after the handler returns successfully.

Subscription is fan-out: each processor has its own cursor, its own subscribed
event types, and its own config. The dispatcher never blocks one processor on
another. There is no shared dispatcher state on `file_events` rows.

#### Processor invariants

The cursor-only-on-success model trades per-event DB diagnostics for "cursor
lag + logs." That trade is sound iff the following invariants hold for every
processor `kind`:

- **Handler idempotency over `event_id`.** If a worker succeeds at the work
  but crashes before committing the cursor, the next dispatcher tick re-enqueues
  the same event. Handlers must produce the same observable result on the
  second run. `meta_extract` overwrites `File.meta` deterministically; external
  sinks must use a downstream idempotency key (e.g. `event_id`) so retries are
  deduped.
- **Per-processor concurrency = 1.** The cursor is a single integer; advancing
  it in order requires sequential execution per processor. Serial per
  processor, parallel across processors. Enforced by the warm worker's per-
  function concurrency setting.
- **Cursor commit transactionality.** For DB-side-effect handlers the cursor
  `UPDATE processors SET last_committed_offset = N` happens in the same
  transaction as the side effect (e.g. `File.meta` update). For network-side-
  effect handlers (webhook, SQS, Kafka) the cursor commits *after* the network
  call returns success — at-least-once semantics, downstream dedupes.
- **In-flight dedup at the queue.** arq `_job_id = f"{processor_id}:{event_id}"`
  is the only mechanism preventing dispatcher tick #2 from re-enqueueing an
  in-flight job. Handler idempotency covers the corner case where the dedup
  TTL expires before the worker finishes.
- **Head-of-line blocking is accepted.** A permanently failing event blocks
  its processor's cursor until an admin intervenes. The escape hatch is the
  admin "skip stuck event" action, which writes a `processor.cursor.skipped`
  row to `audit_events` (with actor, reason, processor name, and skipped
  offset) and then advances `last_committed_offset` past the bad event. Every
  skip is auditable; there is no silent forward-jump.
- **Processor outcome events.** Processors emit
  `processor.<substrate>.completed` or `processor.<substrate>.failed`
  `file_events` rows when they finish, so external consumers can react to
  "metadata is now ready" the same way internal subscribers do. The failure
  variant is emitted before the cursor stalls and before any skip action.
- **Per-`kind` config validation.** The shape of `processors.config` depends
  on `kind`. Each `kind` registers a pydantic config model alongside its
  handler; rows are validated on insert/update so `config` JSONB cannot rot
  into a junk drawer.

### Health and Operations

The deployment surface needs production-grade health signals and operational
guardrails.

- Implement `/healthz` and `/readyz`.
- Expose API, database, Redis, processing worker, maintenance worker, and
  object-store readiness.
- Add clear startup checks for missing secrets and unsafe production defaults.
- Add worker status visibility for both the processing and maintenance queues,
  including queue depth, oldest pending job age, and per-processor cursor lag
  versus the head of `file_events`.

## Event and Processor Tables

Relic uses three event tables and one processor-registry table, each with a
distinct audience, write path, and retention strategy. Together they form the
durable substrate the warm and cold paths consume.

`EVENT_RETENTION_DAYS` is the single retention knob applied across all three
event tables; per-table retention can be split out later if it becomes
necessary. The `processors` table is registry data, not event data, and is
not subject to retention.

### `audit_events` — actor-driven admin and identity log

Existing table. Records actions performed by a human or programmatic actor on
the administrative surface: users, access keys, buckets, folder grants, and
authentication outcomes. Audit rows are written in the same transaction as the
canonical mutation. Audit is **not** the activity stream; external sinks do not
subscribe to it.

Event kinds (`operation` column):

- `auth.login`, `auth.logout`, `auth.login_failed`
- `user.created`, `user.updated`, `user.deleted`
- `access_key.created`, `access_key.revoked`
- `bucket.created`, `bucket.updated`, `bucket.deleted`
- `folder.access.granted`, `folder.access.revoked`, `folder.access.changed`
- `processor.created`, `processor.updated`, `processor.deleted`,
  `processor.enabled`, `processor.disabled`, `processor.cursor.rewound`,
  `processor.cursor.skipped`

The current envelope (id, created_at, updated_at, operation, status,
actor_user_id, request_id, file_ids[], folder_ids[], blob_ids[], meta) stays
as-is.

`processor.cursor.skipped` rows are the auditable record of the admin
"skip stuck event" escape hatch. `meta` carries `processor_name`,
`skipped_offset`, the `event_id` of the bad event, and the actor-supplied
`reason`. `processor.cursor.rewound` records the equivalent for replay-style
rewinds (cursor moved backwards rather than forwards).

### `file_events` — the warm outbox

New table. Source of truth for "something happened to a file, folder, or
content-side processor outcome." Written in the same transaction as the
canonical mutation. Consumed by the warm outbox dispatcher, which fans out
one `relic:processing` job per `(event_id, processor_name)` pair.

External sinks (webhooks, SQS, Kafka, NATS, object-store batches) subscribe to
`file_events` through the same mechanism Relic's internal processors use.

Event kinds (`event_type` column):

Content events, emitted in the same transaction as the canonical mutation:

- `file.created`
- `file.updated` (overwrite that swaps in a new blob)
- `file.metadata.updated` (canonical `File.meta` changed)
- `file.moved` (same `file_id`, new folder and/or name)
- `file.copied` (new `file_id`, same content)
- `file.deleted`
- `folder.created`
- `folder.updated` (rename or policy change)
- `folder.moved`
- `folder.deleted`

Processor outcome events, emitted by warm workers when they finish:

- `processor.meta_extract.completed`
- `processor.meta_extract.failed`
- `processor.preview.completed` (future)
- `processor.preview.failed` (future)
- `processor.thumbnail.completed` (future)
- `processor.thumbnail.failed` (future)

Explicitly **not** in `file_events`:

- `object.get`, `object.head`, `object.put`, `object.deleted`, `object.copied`
  (the S3-protocol read/write surface) — Prometheus only. S3 writes still
  produce `file.*` events through the canonical service layer.
- `blob.*` (refcount, migration, purge churn) — `maintenance_events` only.
- `bucket.probed` — Prometheus + `maintenance_events`.
- `user.*`, `access_key.*`, `bucket.created/updated/deleted` — `audit_events`.

Envelope:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `uuid` PK | |
| `offset` | `BIGSERIAL UNIQUE` | Monotonic replay cursor primitive. Do not derive cursors from `created_at`. |
| `created_at` | `timestamptz` | `default now()` |
| `schema_version` | `int` | Starts at `1`. Bump only for incompatible envelope changes; payloads are extended additively within a version. |
| `event_type` | `text` | e.g. `file.created`. |
| `status` | `text` | `succeeded` / `failed`. Only meaningful for `processor.*` kinds. |
| `actor_user_id` | `uuid` FK | `ON DELETE SET NULL`. NULL for system-emitted rows. |
| `request_id` | `text` | Carries the originating request through async hops. |
| `idempotency_key` | `text` UNIQUE | Nullable. Lets API callers dedupe retries. |
| `file_id` | `uuid` FK | `ON DELETE SET NULL`, indexed. NULL for `folder.*` events. |
| `folder_id` | `uuid` FK | `ON DELETE SET NULL`, indexed. Parent folder for `file.*` events; subject for `folder.*` events. |
| `payload` | `jsonb` | Event-typed body. See below. |

No `dispatched_at` column. The pull-model dispatcher tracks position per
processor via `processors.last_committed_offset`; `file_events` rows are
immutable after insert.

Payload shapes (illustrative, all extended additively within `schema_version=1`):

```jsonc
// file.created
{ "name": "report.pdf", "blob_id": "...", "size_bytes": 1234,
  "mimetype": "application/pdf", "content_hash": "..." }

// file.updated  (overwrite swapped in a new blob)
{ "name": "report.pdf", "previous_blob_id": "...", "blob_id": "...",
  "size_bytes": 1300 }

// file.metadata.updated
{ "changed_keys": ["tags", "keywords", "summary"] }

// file.moved
{ "from_folder_id": "...", "to_folder_id": "...",
  "from_name": "old.pdf", "to_name": "new.pdf" }

// file.copied
{ "source_file_id": "...", "new_file_id": "...", "to_folder_id": "..." }

// file.deleted
{ "folder_id": "...", "name": "report.pdf" }

// folder.created
{ "parent_id": "...", "name": "Reports" }

// folder.moved
{ "from_parent_id": "...", "to_parent_id": "...",
  "from_name": "...", "to_name": "..." }

// processor.meta_extract.completed
{ "processor": "meta_extract",
  "duration_ms": 412, "bytes_read": 4096 }

// processor.meta_extract.failed
{ "processor": "meta_extract",
  "duration_ms": 88,
  "error_class": "ValueError",
  "error_message": "Parser metadata invalid: ..." }
```

### `maintenance_events` — internal cold-path log

New table. Resource-level outcomes of cold-path workers. Not an outbox: nothing
reads it to fire more work. External sinks never see it. Lives behind an admin
UI for forensics ("why did this blob land in cold storage 14 days ago?").

Event kinds (composed of `job` + `action`):

| `job` | `action` values |
| --- | --- |
| `purge_dereferenced_blobs` | `blob.purged`, `blob.purge_failed` |
| `rebalance_blob_storage` | `blob.migrated`, `blob.migration_skipped`, `blob.migration_failed` |
| `bucket_probe` | `bucket.probe_ok`, `bucket.probe_failed` |
| `trim_audit_events` | `audit.trimmed` |
| `trim_file_events` | `file_event.trimmed` (future) |
| `trim_maintenance_events` | `maintenance_event.trimmed` (future) |
| `reconcile_bucket_drift` | `blob.reconciled`, `blob.reconcile_mismatch` (future) |

One row per resource-level outcome, not one row per batch. `batch_id` groups
all rows from a single cron firing.

Envelope:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `uuid` PK | |
| `created_at` | `timestamptz` | `default now()` |
| `job` | `text` | e.g. `rebalance_blob_storage`. Indexed. |
| `action` | `text` | e.g. `blob.migrated`. Indexed. |
| `status` | `text` | `succeeded` / `failed` / `skipped`. |
| `batch_id` | `uuid` | Groups events from one cron firing. Indexed. |
| `bucket_id` | `uuid` FK | `ON DELETE SET NULL`. NULL when not bucket-scoped. |
| `blob_id` | `uuid` | **Not** a foreign key — blob row may be gone by the time we log. |
| `duration_ms` | `int` NULL | |
| `meta` | `jsonb` | Action-specific details. |

`maintenance_events` has no `actor_user_id`, no `request_id`, no `offset`, and
no `dispatched_at`. It is system-emitted, untriggered by any request, and not
consumed by anyone.

`meta` examples by action:

```jsonc
// blob.purged
{ "freed_bytes": 1048576, "bucket_key": "ab/cd/..." }

// blob.migrated
{ "from_bucket_id": "...", "to_bucket_id": "...",
  "from_tier": 1, "to_tier": 2,
  "reason": "lifecycle.cooldown", "size_bytes": 1048576 }

// blob.migration_skipped
{ "from_bucket_id": "...", "reason": "destination_full",
  "size_bytes": 1048576 }

// bucket.probe_ok
{ "put_ms": 12, "head_ms": 4, "get_ms": 7, "delete_ms": 5 }

// bucket.probe_failed
{ "phase": "head", "error_class": "BotoCoreError",
  "error_message": "..." }

// audit.trimmed
{ "retention_days": 90, "deleted_rows": 1234 }
```

### `processors` — registry, configuration, and cursor

New table. The first-class home for every warm-path subscriber: internal
processors (`meta_extract`, future `preview`, `thumbnail`, `text_extract`,
`stats_rollup`) and external sinks (`webhook:*`, `sqs:*`, `kafka:*`,
`object_store:*`) are all rows in this table. The dispatcher pulls events
past each row's cursor; the worker advances the cursor only on success.

The table holds three things together: **identity**, **configuration**, and
**state (the cursor)**. Identity and configuration are admin-managed (or
seed-managed for first-party substrates like `meta_extract`); state is
worker-managed.

Envelope:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `uuid` PK | |
| `created_at`, `updated_at` | `timestamptz` | |
| `name` | `text` UNIQUE | Stable handle, e.g. `meta_extract`, `webhook:acme`. Used in logs, metrics labels, and `_job_id`. |
| `kind` | `text` | Discriminator that resolves to a code handler. Values: `meta_extract`, `preview`, `thumbnail`, `text_extract`, `stats_rollup`, `webhook`, `sqs`, `kafka`, `object_store`. Rows with unknown `kind` are a configuration error caught at dispatcher startup. |
| `enabled` | `bool` | Operational pause/resume. Dispatcher skips disabled rows. |
| `source` | `text` | `seed` or `admin`. Seed-managed rows are upserted from `server/seed.py`; admin edits to `seed`-sourced rows are blocked in the API except for `enabled` and `last_committed_offset`. |
| `subscribed_event_types` | `text[]` | e.g. `["file.created", "file.updated", "file.metadata.updated"]`. Dispatcher filters on this. |
| `config` | `jsonb` | Kind-specific. Validated against a pydantic model registered alongside each `kind`. |
| `last_committed_offset` | `bigint` | Default `0`. Advanced by the worker after a successful handler. `UPDATE` is the operation that both replays (rewind) and skip-stuck-event (forward jump) use. |
| `last_committed_at` | `timestamptz` NULL | Wall-clock view of cursor progress. |

Indexes:

```
PRIMARY KEY (id)
UNIQUE      (name)
INDEX       (enabled, kind)
```

`config` shapes per `kind` (illustrative; the canonical shape is the registered
pydantic model):

```jsonc
// kind=meta_extract
{ "byte_caps": { "image": 134217728, "pdf": 134217728, "text": 16777216, "... per-toolchain ...": 0 } }

// kind=webhook
{ "url": "https://...", "signing_secret_ref": "kms:...",
  "headers": { "X-Tenant": "acme" }, "timeout_seconds": 10 }

// kind=sqs
{ "queue_url": "https://sqs....", "region": "us-west-2",
  "credential_ref": "secret:..." }

// kind=preview
{ "max_dimension_px": 1024, "formats": ["webp"] }
```

Seeded rows (created by `server/seed.py` next to the admin user and root
folder):

- `meta_extract` — `kind=meta_extract`, `enabled=true`, `source=seed`,
  subscribed to `["file.created", "file.updated"]`,
  `last_committed_offset=0` on first deploy so existing files backfill.

Admin-managed rows (created from the admin UI at runtime):

- All external sinks (`webhook:*`, `sqs:*`, etc.).
- Optional internal processors that are deployed but not seeded.

The pull-model dispatcher and the cursor-only-on-success contract replace the
per-attempt log we previously considered. Diagnostics now come from:

- **Cursor lag** per processor (`max(file_events.offset) - processors.last_committed_offset`),
  surfaced in the admin UI and as a Prometheus gauge. A lag above a configured
  threshold (default: 100) flags a processor as stalled.
- **Operational logs and Prometheus**, where per-event error detail lives.
- **`audit_events.processor.cursor.skipped`** rows, which give every admin
  cursor jump a permanent, queryable record.

A per-attempt diagnostic table will be reintroduced if and when external sinks
require head-of-line-blocking relief (see Open Product Questions).

## Platform Layer

### External Activity Delivery

External systems subscribe to `file_events` (not `audit_events`, not
`maintenance_events`). The activity contract is:

- Monotonic `offset` per row gives consumers a stable replay cursor.
- `schema_version` plus event-typed `payload` defines a stable, versioned
  envelope.
- At-least-once delivery with consumer-side idempotency on `idempotency_key`
  (or `event_id` if the caller did not supply one).
- High-volume read activity (`object.get`, `object.head`, signed-URL fetches)
  stays out of `file_events` and is observable through Prometheus aggregates
  only.

### Activity Replay

Consumers need recovery and backfill paths from the start. Replay is built on
the `file_events.offset` primitive and per-processor cursors.

- Replay from a `file_events.offset` or `created_at` timestamp by writing the
  target offset to `processors.last_committed_offset` for the affected row.
  Every cursor rewind is recorded as an `audit_events.processor.cursor.rewound`
  row with the actor, processor name, old/new offset, and reason.
- Each processor's cursor is its durable consumer checkpoint. There is no
  separate per-subscriber cursor store.
- Support bounded replay scoped by `event_type`, `file_id`, or `folder_id`
  subtree by inserting a short-lived helper processor row, or by replaying
  only the affected rows into the existing processor (cursor advances past
  unrelated events using the same admin skip action).
- Replay reuses the warm dispatcher: rewinding the cursor makes the
  dispatcher's next tick re-enqueue events past the new position. Handler
  idempotency guarantees no canonical-state drift on re-processing.
- Document retention behavior driven by `EVENT_RETENTION_DAYS`. The
  retention-trim job must refuse to delete `file_events` rows whose `offset >
  min(last_committed_offset)` across enabled processors, or else those
  processors permanently miss events. A future compaction policy can replace
  raw retention once long-horizon replay becomes a product requirement.
- Provide an admin tool to rehydrate downstream indexes after outages or
  schema-version bumps by rewinding the relevant processor's cursor.

### Activity Sinks

External delivery substrates are warm-path processors. Each is a row in the
`processors` table with a sink-specific `kind` (`webhook`, `sqs`, `kafka`,
`object_store`) and a `config` payload, and is dispatched through the same
pull loop as internal processors.

- HTTP webhook sink (`kind=webhook`) with request signing, exponential
  backoff inside the handler, and per-event audit through
  `processor.<substrate>.failed` events.
- SQS-compatible sink (`kind=sqs`).
- Kafka or NATS sink (`kind=kafka`) for infrastructure users.
- Object-store sink (`kind=object_store`) that writes event batches to a
  configured bucket.
- Admin UI for creating sinks (CRUD on `processors`), pausing them
  (`enabled=false`), rewinding cursors, executing the "skip stuck event"
  action, inspecting cursor lag, and viewing the audit trail of cursor
  changes.

Because the cursor-only-on-success model has **head-of-line blocking** — a
permanently failing event halts its processor's cursor until an admin
intervenes — external sinks targeting unreliable downstreams may eventually
need a lighter-weight dead-letter mechanism. The Open Product Questions
section tracks when to reintroduce one.

### Prometheus Metrics

Relic exposes operational performance data through a Prometheus scrape
endpoint. Event tables answer "what happened" with full-fidelity, queryable
history; metrics answer "how is the system performing" with low-cardinality
aggregates. High-volume read paths (S3 `GET` / `HEAD`, signed-URL fetches)
only live in metrics — they never write to `file_events`.

Initial endpoint:

- `/metrics` for Prometheus-compatible counters, histograms, and gauges.

Gateway metrics:

- `relic_gateway_requests_total{operation,status,bucket,tier}`
- `relic_gateway_duration_seconds{operation,status,bucket,tier}`
- `relic_gateway_bytes_total{operation,direction,bucket,tier}`
- `relic_gateway_range_requests_total{operation,status,bucket,tier}`
- `relic_backend_duration_seconds{operation,phase,status,bucket,tier}`
- `relic_backend_errors_total{operation,phase,bucket,tier,error_class}`
- `relic_event_write_duration_seconds{table,event_type,status}` (covers
  `audit_events`, `file_events`, `maintenance_events`)

API metrics:

- `relic_api_requests_total{route,operation,status}`
- `relic_api_duration_seconds{route,operation,status}`
- `relic_api_payload_bytes_total{route,direction,status}`
- `relic_api_audit_write_duration_seconds{route,operation,status}`

Processor and maintenance metrics:

- `relic_processor_jobs_total{processor,kind,status}`
- `relic_processor_duration_seconds{processor,kind,status}`
- `relic_processor_queue_depth{queue}` (labels: `relic:processing`,
  `relic:maintenance`)
- `relic_processor_queue_wait_seconds{processor}`
- `relic_processor_cursor_lag{processor,kind}` — gauge of
  `max(file_events.offset) - processors.last_committed_offset`. Primary
  stalled-processor signal.
- `relic_processor_cursor_age_seconds{processor,kind}` — gauge of
  `now() - processors.last_committed_at`. Catches processors that completed
  recently but have stalled on a stuck event.
- `relic_processor_cursor_skips_total{processor,kind}` — counter incremented
  by the admin skip-stuck-event action.
- `relic_meta_extract_bytes_total{toolchain,status}`
- `relic_meta_extract_duration_seconds{toolchain,status}`
- `relic_maintenance_batches_total{job,status}`
- `relic_maintenance_duration_seconds{job,status}`
- `relic_maintenance_rows_total{job,action,outcome}` (matches
  `maintenance_events.action`)
- `relic_bucket_probe_duration_seconds{bucket,tier,operation,status}`
- `relic_bucket_capacity_bytes{bucket,tier,state}`

Cardinality rules:

- Safe labels include operation, route template, status, bucket, tier, phase,
  processor, toolchain, queue, and coarse object size band.
- Avoid file ID, folder ID, user ID, request ID, object key, MIME type, and raw
  error message labels.
- Store high-cardinality identity in `audit_events`, `file_events`,
  `maintenance_events`, and logs; correlate via `request_id`.
- Use OpenTelemetry traces later for sampled per-request timing forensics
  rather than persisting every timing breakdown in PostgreSQL.

### Observability and Storage Intelligence

Storage intelligence is derived from the durable substrates plus canonical
tables:

| Source | Best at |
| --- | --- |
| Canonical tables (`files`, `folders`, `blobs`, `buckets`) | Current-state queries: who owns what, what is placed where. |
| `audit_events` | Actor and admin forensics, including every processor cursor change. |
| `file_events` | Content history, derived rollups, external delivery. |
| `maintenance_events` | Lifecycle forensics: why a blob moved, when a probe failed, what a purge batch did. |
| `processors` | Per-substrate cursor position, config, enabled state, lag. |
| Prometheus | Aggregate latency, error rate, throughput, queue depth, cursor lag, and high-volume read activity. |
| Operational logs | Per-event handler errors that previously lived in a per-attempt table. |

Derived views:

- Folder-level storage usage, file counts, blob counts, and dedupe savings.
- Folder-level placement breakdown by storage tier and backing bucket.
- Bucket latency history and error rates from Prometheus.
- Gateway overhead analysis from gateway and backend duration histograms.
- Latency percentiles by low-cardinality dimensions such as operation, bucket,
  tier, status, and object size band.
- Bucket probe failures and capacity pressure from Prometheus +
  `maintenance_events` (`bucket.probe_failed`).
- Processor health from `processors.last_committed_offset`,
  `processors.last_committed_at`, and `relic_processor_cursor_lag`. Alerts
  fire when a processor's lag exceeds its configured threshold (default 100).
- Per-file diagnostics by joining `file_events` (event row) with operational
  logs filtered by `processor_name` and `event_id` — the cursor model means
  per-event failure detail lives in logs, not a DB table.
- Lifecycle movement history from `maintenance_events` (`blob.migrated`,
  `blob.purged`), including why a blob moved and which policy drove the
  decision.
- Admin views that explain effective storage policy inheritance for folders.
- Derived rollups maintained incrementally from `file_events` where that is
  cheaper than computing from canonical tables on every request.

## Storage and S3 Compatibility

### S3 Gateway Coverage

The current gateway focuses on object operations. Broader compatibility would
make Relic easier to use with existing tooling.

- `ListBuckets`.
- `HeadBucket`.
- `ListObjectsV2` with prefixes, delimiters, pagination, and continuation
  tokens.
- Multipart upload lifecycle.
- Compatibility testing against common clients such as AWS CLI, boto3, rclone,
  and DuckLake.

### Import and Sync

Relic needs a path for existing data, not only new uploads.

- Import an existing S3 bucket into Relic metadata.
- Preserve object keys as folder paths.
- Optionally parse imported files after registration.
- Detect drift between Relic metadata and backing bucket contents.
- Support resumable import jobs with progress and failure reporting.

### Quotas, Retention, and Guardrails

Administrators need controls that prevent accidental cost, data loss, and abuse.

- Per-folder, per-user, and global storage quotas.
- Maximum upload size.
- Allowed and blocked MIME types or extensions.
- Retention periods and deletion protection.
- Legal hold or freeze semantics for selected folders.
- Policy violation reporting in the UI and API.

### Versioning

Files currently behave like single logical references. Version history would
make Relic safer as a system of record.

- File version creation on overwrite or explicit upload.
- Restore previous versions.
- Compare metadata between versions.
- Retention rules for old versions.
- Search behavior that can target latest versions or all versions.

## User Experience

### Preview and Enrichment UX

Processed metadata should become more visible and useful to users.

- Image thumbnails.
- Text previews for readable documents.
- PDF and document preview paths.
- Audio and video technical metadata display.
- Processor failure details and manual reprocess actions.
- Clear explanations for tags, keywords, summaries, and key/value fields.

### Admin File and Blob Inspection

The admin routes for files and blobs are currently placeholders. They should
become operational inspection tools.

- Logical file inventory with filters for owner, folder, parse status, size,
  and metadata.
- Physical blob inventory with bucket, tier, refcount, size, content hash, and
  accessed timestamp.
- Blob-to-file reference inspection.
- Manual purge or repair workflows with strong safety checks.
- Storage migration status and retry controls.

## Open Product Questions

- Which Prometheus labels are worth supporting at launch, and what cardinality
  budget should Relic enforce?
- Should Relic add OpenTelemetry tracing for sampled per-request timing
  forensics, or are Prometheus aggregates enough initially?
- What is the intended external integration target: internal services, data
  lake tooling, desktop sync clients, or all of them?
- Should folder-level stats be computed synchronously, cached, or maintained
  incrementally from `file_events`?
- How much S3 compatibility is required before advertising Relic as an
  S3-compatible gateway?
- When does it become necessary to split `EVENT_RETENTION_DAYS` per table
  (audit kept long, `file_events` aggressively compacted, maintenance kept
  medium-term)?
- Long-horizon `file_events` replay: do we ship a separate compacted snapshot
  table once `EVENT_RETENTION_DAYS` cannot honor a desired replay window?
- When does head-of-line blocking on external sinks become painful enough to
  reintroduce a dead-letter mechanism? Candidates: a lightweight
  `processor_skipped_events(processor_id, event_id, reason, created_at)`
  table, a per-processor `auto_skip_after_n_retries` config option, or the
  fuller `processor_attempts` table we initially considered. The first
  external sink that targets an unreliable third-party endpoint is the
  trigger.
- Should the retention-trim job hard-refuse to delete `file_events` rows past
  the slowest enabled processor's cursor, or should it warn loudly and trim
  anyway with a configured grace window? Hard-refuse is safer; warn-and-trim
  avoids a paused processor blocking storage reclamation.
