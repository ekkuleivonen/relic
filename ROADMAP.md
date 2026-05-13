# Relic Roadmap

This roadmap captures the next product layers that would make Relic feel less
like a file manager and more like dependable storage infrastructure.

The async processor architecture (hot/warm/cold tiers, `audit_events`,
`file_events`, `maintenance_events`, `processors` registry, pull-model
dispatcher, `meta_extract` substrate, audited rewind / skip-stuck-event
admin actions) is **live**. Its design contract lives in `README.md` under
"Event Log and Processors". This roadmap covers what extends or builds on
top of that substrate.

## Near Term

### Health and Operations

The deployment surface needs production-grade health signals and
operational guardrails.

- `/healthz` and `/readyz` are shipped.
- `/readyz` exposes API, database, Redis queue, processor registry, object-store
  probe-state, and configuration readiness.
- Configuration readiness warns on local-development defaults for secrets.
- Worker status visibility is partially shipped through queue depth and oldest
  pending job age for both queues. Processor admin/API visibility includes
  cursor, head offset, pending count, failure state, and last commit time.
  Remaining work: explicit worker heartbeat state and Prometheus gauges for
  queue and processor lag.
- Prometheus-compatible `/metrics` has not shipped yet. The metric families in
  "Observability and Metrics" are the planned scrape contract, not current API
  surface.

After health/readiness, prioritize native S3 gateway authentication and
compatibility testing if the immediate goal is client compatibility. Pick
Prometheus metrics if operational alerting is the bigger need, external
activity sinks if downstream event delivery becomes more urgent, or admin
file/blob inspection if operator inventory is the bigger UX gap.

## Platform Layer

### External Activity Sinks

External delivery substrates are warm-path processors. Each is a row in the
`processors` table with a sink-specific `kind` (`webhook`, `sqs`, `kafka`,
`object_store`) and a `config` payload, and is dispatched through the same
pull loop as `meta_extract`. The first external sink is the moment Relic
becomes a streaming platform for downstream consumers, not just an internal
metadata enricher.

- HTTP webhook sink (`kind=webhook`) with request signing, exponential
  backoff inside the handler, and per-event audit via
  `processor.webhook.failed` events.
- SQS-compatible sink (`kind=sqs`).
- Kafka or NATS sink (`kind=kafka`) for infrastructure users.
- Object-store sink (`kind=object_store`) that writes event batches to a
  configured bucket.
- Processor admin CRUD, pause/resume, cursor rewind, skip-stuck-event, cursor
  lag inspection, and cursor audit trail views are shipped. The remaining
  admin work is sink-specific creation/editing affordances once the sink kinds
  themselves exist.

The activity contract external sinks consume:

- Monotonic `file_events.offset` per row gives consumers a stable replay
  cursor.
- `schema_version` plus event-typed `payload` defines a stable, versioned
  envelope.
- At-least-once delivery with consumer-side idempotency on
  `idempotency_key` (or `event_id` if the caller did not supply one).
- High-volume read activity (`object.get`, `object.head`, signed-URL
  fetches) stays out of `file_events` and is observable through Prometheus
  aggregates only.

Because the cursor-only-on-success model has **head-of-line blocking**, a
permanently failing event halts its processor's cursor until an admin
intervenes. External sinks targeting unreliable downstreams may eventually
need a lighter-weight dead-letter mechanism — see Open Product Questions.

### Activity Replay

Consumers need recovery and backfill paths from the start. Replay is built
on the `file_events.offset` primitive and per-processor cursors.

- Replay from a `file_events.offset` or `created_at` timestamp by writing
  the target offset to `processors.last_committed_offset` for the affected
  row. Every cursor rewind is recorded as an
  `audit_events.processor.cursor.rewound` row with the actor, processor
  name, old/new offset, and reason. (Cursor rewind primitive: shipped.
  Bounded-replay tooling around it: planned.)
- Bounded replay scoped by `event_type`, `file_id`, or `folder_id` subtree
  by inserting a short-lived helper processor row, or by replaying only the
  affected rows into the existing processor (cursor advances past unrelated
  events using the same admin skip action).
- Replay reuses the warm dispatcher: rewinding the cursor makes the
  dispatcher's next tick re-enqueue events past the new position. Handler
  idempotency guarantees no canonical-state drift on re-processing.
- A future compaction policy can replace raw retention once long-horizon
  replay becomes a product requirement.
- Admin tool to rehydrate downstream indexes after outages or
  `schema_version` bumps by rewinding the relevant processor's cursor.

### Future processor substrates

The warm-path runtime is generic; the immediate substrates beyond
`meta_extract` and the external sinks above are:

- `preview` — render preview assets for documents and images.
- `thumbnail` — generate thumbnails for image-like content.
- `text_extract` — extract searchable plain text from PDFs and other
  binary text containers.
- `stats_rollup` — incremental folder-level rollups (file counts, total
  size, placement breakdown) maintained from `file_events` rather than
  re-computed on every request.

Each substrate registers a `kind`, a pydantic config model, and a handler
under `server/processors/<substrate>/`, and is seeded into the `processors`
table when first-party.

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
- Latency percentiles by low-cardinality dimensions such as operation,
  bucket, tier, status, and object size band.
- Bucket probe failures and capacity pressure from Prometheus +
  `maintenance_events` (`bucket.probe_failed`).
- Processor health from `processors.last_committed_offset`,
  `processors.last_committed_at`, and `relic_processor_cursor_lag`. Alerts
  fire when a processor's lag exceeds its configured threshold (default
  100).
- Per-file diagnostics by joining `file_events` (event row) with
  operational logs filtered by `processor_name` and `event_id` — the cursor
  model means per-event failure detail lives in logs, not a DB table.
- Lifecycle movement history from `maintenance_events` (`blob.migrated`,
  `blob.purged`), including why a blob moved and which policy drove the
  decision.
- Admin views that explain effective storage policy inheritance for
  folders.
- Derived rollups maintained incrementally from `file_events` where that is
  cheaper than computing from canonical tables on every request.

## Storage and S3 Compatibility

### S3 Gateway Coverage

The gateway now covers the core object, bucket, listing, and multipart flows
that Relic itself exercises. Broader authentication and client compatibility
would make it easier to use with existing tooling.

- `ListBuckets` (shipped).
- `HeadBucket` (shipped).
- `ListObjectsV2` with prefixes, delimiters, pagination, and continuation
  tokens (shipped).
- Live compatibility smoke harness for current presigned-URL gateway flows
  (shipped).
- Multipart upload lifecycle (shipped).
- Access-key `Authorization` header authentication for normal S3 clients
  (planned). The current supported flows use Relic presigned SigV4 query URLs.
- Compatibility testing against common clients such as AWS CLI, boto3,
  rclone, and DuckLake after header authentication lands.

### Import and Sync

Relic needs a path for existing data, not only new uploads.

- Import an existing S3 bucket into Relic metadata.
- Preserve object keys as folder paths.
- Optionally enrich imported files after registration (via `meta_extract`
  through the standard `file.created` event path).
- Detect drift between Relic metadata and backing bucket contents.
- Support resumable import jobs with progress and failure reporting.

### Quotas, Retention, and Guardrails

Administrators need controls that prevent accidental cost, data loss, and
abuse.

- Per-folder, per-user, and global storage quotas.
- Maximum upload size.
- Allowed and blocked MIME types or extensions.
- Retention periods and deletion protection.
- Legal hold or freeze semantics for selected folders.
- Policy violation reporting in the UI and API.

### Versioning

Files currently behave like single logical references. Version history
would make Relic safer as a system of record.

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

The admin file and blob UI pages are currently placeholders. They should
become operational inspection tools that make the existing file/blob state and
storage placement easier to inspect.

- Logical file inventory with filters for owner, folder, metadata
  extraction status, size, and metadata.
- Physical blob inventory with bucket, tier, refcount, size, content hash,
  and accessed timestamp.
- Blob-to-file reference inspection.
- Manual purge or repair workflows with strong safety checks.
- Storage migration status and retry controls.

## Observability and Metrics

### Prometheus Metrics

Relic should expose operational performance data through a Prometheus scrape
endpoint. Today, the durable event tables and readiness endpoint are live;
the Prometheus endpoint and metric families below are still planned.

Event tables answer "what happened" with full-fidelity, queryable history;
metrics answer "how is the system performing" with low-cardinality aggregates.
High-volume read paths (S3 `GET` / `HEAD`, signed-URL fetches) should only
live in metrics — they should never write to `file_events`.

Planned endpoint:

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
  stalled-processor signal; pairs with `relic_processor_cursor_age_seconds`
  to catch "recently progressed but now stuck" cases.
- `relic_processor_cursor_age_seconds{processor,kind}` — gauge of
  `now() - processors.last_committed_at`.
- `relic_processor_cursor_skips_total{processor,kind}` — counter
  incremented by the admin skip-stuck-event action.
- `relic_meta_extract_bytes_total{toolchain,status}`
- `relic_meta_extract_duration_seconds{toolchain,status}`
- `relic_maintenance_batches_total{job,status}`
- `relic_maintenance_duration_seconds{job,status}`
- `relic_maintenance_rows_total{job,action,outcome}` (matches
  `maintenance_events.action`)
- `relic_bucket_probe_duration_seconds{bucket,tier,operation,status}`
- `relic_bucket_capacity_bytes{bucket,tier,state}`

Cardinality rules:

- Safe labels include operation, route template, status, bucket, tier,
  phase, processor, toolchain, queue, and coarse object size band.
- Avoid file ID, folder ID, user ID, request ID, object key, MIME type, and
  raw error message labels.
- Store high-cardinality identity in `audit_events`, `file_events`,
  `maintenance_events`, and logs; correlate via `request_id`.
- Use OpenTelemetry traces later for sampled per-request timing forensics
  rather than persisting every timing breakdown in PostgreSQL.

## Open Product Questions

- Which Prometheus labels are worth supporting at launch, and what
  cardinality budget should Relic enforce?
- Should Relic add OpenTelemetry tracing for sampled per-request timing
  forensics, or are Prometheus aggregates enough initially?
- What is the intended external integration target: internal services, data
  lake tooling, desktop sync clients, or all of them?
- Should folder-level stats be computed synchronously, cached, or
  maintained incrementally from `file_events`?
- How much S3 compatibility is required before advertising Relic as an
  S3-compatible gateway?
- When does it become necessary to split `EVENT_RETENTION_DAYS` per table
  (audit kept long, `file_events` aggressively compacted, maintenance kept
  medium-term)?
- Long-horizon `file_events` replay: do we ship a separate compacted
  snapshot table once `EVENT_RETENTION_DAYS` cannot honor a desired replay
  window?
- When does head-of-line blocking on external sinks become painful enough
  to reintroduce a dead-letter mechanism? Candidates: a lightweight
  `processor_skipped_events(processor_id, event_id, reason, created_at)`
  table, a per-processor `auto_skip_after_n_retries` config option, or the
  fuller `processor_attempts` table we initially considered. The first
  external sink that targets an unreliable third-party endpoint is the
  trigger.
- Should the retention-trim job hard-refuse to delete `file_events` rows
  past the slowest enabled processor's cursor (current behavior), or warn
  loudly and trim anyway with a configured grace window? Hard-refuse is
  safer; warn-and-trim avoids a paused processor blocking storage
  reclamation.
- DB drift: `files.meta` search indexes (`ix_files_meta_extension`,
  `ix_files_meta_keywords`, `ix_files_meta_mimetype`, `ix_files_meta_tags`)
  exist in the database but are not declared on the SQLAlchemy model. They
  are used by file search and were intentionally left untouched by recent
  migrations. Either declare them as expression indexes on the model or
  recreate them through a dedicated migration so autogenerate stops
  flagging them as drift.
