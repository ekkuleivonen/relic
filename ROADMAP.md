# Relic Roadmap

This roadmap captures the next product layers that would make Relic feel less
like a file manager and more like dependable storage infrastructure.

## Near Term

### Durable Event and Audit Foundation

Relic should establish an append-only event foundation before building folder
analytics or storage intelligence. Audit logging can then become both a
human-readable security surface and the raw material for later rollups.

Core principles:

- Persist an event row in PostgreSQL in the request path for every successful
  gateway and API operation, including high-volume reads such as GET and HEAD.
- For mutating operations, write the event row in the same transaction as the
  filesystem, access, user, bucket, or metadata mutation.
- For read-only operations, write a durable event in its own transaction before
  considering the request complete, so access history is not best-effort
  queue-only telemetry.
- Treat ARQ as the processor and delivery layer, not as the source of truth for
  auditability.
- Enqueue processors by `event_id`, so queue outages can be recovered by
  scanning persisted unprocessed events.
- Keep request handling synchronous only for the work needed to preserve core
  invariants: object bytes are confirmed in backing storage before a successful
  file reference is committed, and committed references should not point at
  missing bytes.
- Store stable, versioned event payloads with enough context for audit,
  analytics, replay, and external integrations.
- Keep performance measurements out of the durable event payload by default.
  Relic should expose operational timings and byte counters as Prometheus
  metrics instead, with request IDs bridging events, logs, and future traces.

Initial event envelope:

```json
{
  "source": "s3_gateway",
  "operation": "PUT",
  "status": "succeeded",
  "actor_user_id": "...",
  "request_id": "...",
  "file_ids": ["..."],
  "folder_ids": ["..."],
  "blob_ids": ["..."],
  "metadata": {
    "bucket": "photos",
    "key": "2026/a.jpg",
    "etag": "..."
  }
}
```

Audit coverage:

- User login/logout events.
- S3 gateway object events: PUT, GET, HEAD, DELETE, COPY, and future multipart
  lifecycle operations.
- Relic API file events: upload, download, copy, move, rename, metadata update,
  and delete.
- Folder create, copy, move, rename, delete, and policy-change events.
- Folder access grant, update, and revoke events.
- Access key creation and revocation events.
- Bucket backend creation, update, probe, and deletion events.
- Processor and maintenance events such as metadata parsing, blob migration,
  dereferenced blob purge, and retention trimming.

Audit product surface:

- Admin UI for filtering audit records by actor, target, folder, event type,
  source, status, and time range.
- Clear distinction between high-volume access events, such as GET/download,
  and lower-volume mutation/security events, while still persisting both.
- Configurable retention by event category.
- A path to derive `audit_events` as a human-readable projection over the
  durable technical event stream.

### Async Processors

The current parser workers should become a broader processor system. Parsing is
one processor type; audit materialization, event delivery, previews, stats
rollups, and storage maintenance can use the same pattern.

Processor responsibilities:

- Parse metadata for file-created or metadata-replaced events.
- Write or update audit projections from durable events.
- Emit follow-up events such as `file.metadata.updated`.
- Deliver events to external sinks.
- Build derived rollups for folder stats and storage usage.
- Generate previews, thumbnails, and extracted text.
- Record processor attempts, failures, and retry state.

Processor design goals:

- Process by `event_id`, not by ad hoc file IDs.
- Keep processor operations idempotent.
- Allow failed processors to be retried without duplicating audit records or
  corrupting metadata.
- Keep parser byte limits and processor retention settings configurable.
- Rename queue and worker concepts from parser-specific naming toward
  processor-oriented naming over time.

### Health and Operations

The deployment surface needs production-grade health signals and operational
guardrails.

- Implement `/healthz` and `/readyz`.
- Expose API, database, Redis, worker, and object-store readiness.
- Add clear startup checks for missing secrets and unsafe production defaults.
- Add worker status visibility for processors and storage maintenance jobs.

## Platform Layer

### Event Sources

Both the S3 gateway and the normal JSON API should emit the same event envelope
for comparable operations.

S3 gateway events should capture:

- `source: "s3_gateway"`.
- The S3 operation, such as PUT, GET, HEAD, DELETE, COPY, and future multipart
  operations.
- Authenticated user and request ID.
- Related file, folder, and blob IDs.
- Gateway metadata such as bucket, key, range request, ETag, and copy source.

Relic API events should capture:

- `source: "relic_api"`.
- The application operation, such as file move, folder rename, access grant, or
  bucket probe.
- Authenticated user and request ID.
- Related file, folder, blob, bucket, access key, or user IDs.
- API metadata needed for audit and replay.

Maintenance workers should emit periodic operational events:

- `blob.purged`
- `blob.migrated`
- `bucket.probed`
- `audit_events.trimmed`
- `events.trimmed`
- Processor retry or failure summaries.

### Durable Event Stream

External systems should be able to subscribe to Relic changes without polling.
This should be a durable feed, not a transient websocket-only stream.

Initial event types:

- `file.created`
- `file.updated`
- `file.deleted`
- `file.moved`
- `file.copied`
- `file.downloaded`
- `file.metadata.updated`
- `folder.created`
- `folder.updated`
- `folder.deleted`
- `folder.moved`
- `folder.access.changed`
- `blob.created`
- `blob.dereferenced`
- `blob.purged`
- `blob.migrated`
- `bucket.created`
- `bucket.updated`
- `bucket.probed`
- `bucket.deleted`
- `object.put`
- `object.head`
- `object.get`
- `object.deleted`
- `object.copied`
- `user.created`
- `user.updated`
- `user.deleted`
- `access_key.created`
- `access_key.revoked`

Design goals:

- Persist events with monotonically increasing offsets or cursors.
- Make event persistence part of the synchronous success path for both reads
  and writes; processors may lag, but the durable event should not.
- Include actor, target, timestamp, tenant or deployment scope, request ID, and
  enough metadata for consumers to decide whether to fetch more detail.
- Keep event payloads stable and versioned.
- Separate internal operational events from external integration events when
  needed.
- Provide clear delivery semantics, likely at-least-once delivery with
  idempotency keys.
- Support high-volume GET/download events with retention controls rather than
  downgrading them to best-effort telemetry.

### Event Replay

Consumers need recovery and backfill paths from the start.

- Replay from an offset, timestamp, or named checkpoint.
- Create durable consumer cursors.
- Support bounded replay for a folder subtree, bucket, user, or event type.
- Document retention windows and compaction rules.
- Provide tools to rehydrate downstream indexes after outages or schema
  changes.

### Event Sinks

The persisted event stream should be the primitive. Product integrations can
then expose common delivery options.

- HTTP webhooks with signing and retry policy.
- SQS-compatible or queue-style sink.
- Kafka or NATS sink for infrastructure users.
- Object-store sink that writes event batches to a bucket.
- Admin UI for configuring sinks, testing delivery, and inspecting failures.

### Prometheus Metrics

Relic should expose operational performance data through a Prometheus scrape
endpoint, not by storing per-request timing details in durable event rows.
Events answer "what happened"; metrics answer "how is the system performing."

Initial endpoint:

- `/metrics` for Prometheus-compatible counters, histograms, and gauges.

Gateway metrics:

- `relic_gateway_requests_total{operation,status,bucket,tier}`
- `relic_gateway_duration_seconds{operation,status,bucket,tier}`
- `relic_gateway_bytes_total{operation,direction,bucket,tier}`
- `relic_gateway_range_requests_total{operation,status,bucket,tier}`
- `relic_backend_duration_seconds{operation,phase,status,bucket,tier}`
- `relic_backend_errors_total{operation,phase,bucket,tier,error_class}`
- `relic_event_write_duration_seconds{source,operation,status}`

API metrics:

- `relic_api_requests_total{route,operation,status}`
- `relic_api_duration_seconds{route,operation,status}`
- `relic_api_payload_bytes_total{route,direction,status}`
- `relic_api_event_write_duration_seconds{route,operation,status}`

Processor and maintenance metrics:

- `relic_processor_jobs_total{processor,status}`
- `relic_processor_duration_seconds{processor,status}`
- `relic_processor_queue_depth{queue}`
- `relic_processor_queue_wait_seconds{processor}`
- `relic_parser_bytes_total{toolchain,status}`
- `relic_parser_duration_seconds{toolchain,status}`
- `relic_maintenance_batches_total{job,status}`
- `relic_maintenance_duration_seconds{job,status}`
- `relic_maintenance_rows_total{job,outcome}`
- `relic_bucket_probe_duration_seconds{bucket,tier,operation,status}`
- `relic_bucket_capacity_bytes{bucket,tier,state}`

Cardinality rules:

- Safe labels include operation, route template, status, bucket, tier, phase,
  processor, toolchain, queue, and coarse object size band.
- Avoid file ID, folder ID, user ID, request ID, object key, MIME type, and raw
  error message labels.
- Store high-cardinality identity in durable events and logs, then correlate via
  `request_id`.
- Use OpenTelemetry traces later for sampled per-request timing forensics rather
  than persisting every timing breakdown in PostgreSQL.

### Observability and Storage Intelligence

Storage intelligence should be derived after the event and audit layer exists,
using the durable stream plus current canonical tables.

- Folder-level storage usage, file counts, blob counts, and dedupe savings.
- Folder-level placement breakdown by storage tier and backing bucket.
- Bucket latency history and error rates from Prometheus metrics.
- Gateway overhead analysis from gateway and backend duration histograms.
- Latency percentiles by low-cardinality dimensions such as operation, bucket,
  tier, status, and object size band.
- Bucket probe failures and capacity pressure.
- Processor queue health and parser failure rates from Prometheus metrics.
- Per-file processor diagnostics from durable events and canonical metadata.
- Lifecycle movement history, including why a blob moved and which policy drove
  the decision.
- Admin views that explain effective storage policy inheritance for folders.
- Derived rollups maintained incrementally from events where that is cheaper
  than computing from canonical tables on every request.

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

- How long should different event categories be retained, especially
  high-volume GET/download events versus mutation and security events?
- Should `audit_events` be a separate table, or a human-readable projection over
  the durable `events` table?
- Which Prometheus labels are worth supporting at launch, and what cardinality
  budget should Relic enforce?
- Should Relic add OpenTelemetry tracing for sampled per-request timing
  forensics, or are Prometheus aggregates enough initially?
- What is the intended external integration target: internal services, data
  lake tooling, desktop sync clients, or all of them?
- Should folder-level stats be computed synchronously, cached, or maintained by
  incremental events?
- How much S3 compatibility is required before advertising Relic as an
  S3-compatible gateway?
- Which processors should be required before an event is considered fully
  handled, and which should be optional best-effort enrichment?
