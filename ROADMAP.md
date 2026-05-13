# Relic Roadmap

This roadmap captures the next product layers that would make Relic feel less
like a file manager and more like dependable storage infrastructure.

## Near Term

### Async Processors

The current parser and maintenance workers should become a broader processor
system. Parsing is one processor type; activity delivery, previews, stats
rollups, and storage maintenance can use the same pattern.

Future processor responsibilities:

- Parse metadata after successful file/object mutations.
- Record processor attempts, failures, and retry state outside the audit log.
- Deliver non-audit activity records to external sinks once that stream exists.
- Build derived rollups for folder stats and storage usage.
- Generate previews, thumbnails, and extracted text.

Processor design goals:

- Process by stable activity IDs or resource IDs rather than ad hoc payloads.
- Keep processor operations idempotent.
- Allow failed processors to be retried without duplicating activity records or
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

### Durable Activity Stream

External systems should be able to subscribe to Relic changes without polling.
Relic already persists admin-facing audit events for identity, access, bucket,
and folder changes. The next step is a separate integration/activity stream for
object/content activity, processor outcomes, and high-volume operational facts
that do not belong in the audit log.

Initial activity types:

- `file.created`
- `file.updated`
- `file.deleted`
- `file.moved`
- `file.copied`
- `file.downloaded`
- `file.metadata.updated`
- `parse.completed`
- `parse.failed`
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

- Persist activity records with monotonically increasing offsets or cursors.
- Include actor, target, timestamp, tenant or deployment scope, request ID, and
  enough metadata for consumers to decide whether to fetch more detail.
- Keep activity payloads stable and versioned.
- Keep audit events separate from high-volume object/content activity.
- Provide clear delivery semantics, likely at-least-once delivery with
  idempotency keys.
- Support high-volume GET/download activity with retention controls rather than
  downgrading them to best-effort telemetry.

### Activity Replay

Consumers need recovery and backfill paths from the start.

- Replay from an offset, timestamp, or named checkpoint.
- Create durable consumer cursors.
- Support bounded replay for a folder subtree, bucket, user, or activity type.
- Document retention windows and compaction rules.
- Provide tools to rehydrate downstream indexes after outages or schema
  changes.

### Activity Sinks

The persisted activity stream should be the primitive. Product integrations can
then expose common delivery options.

- HTTP webhooks with signing and retry policy.
- SQS-compatible or queue-style sink.
- Kafka or NATS sink for infrastructure users.
- Object-store sink that writes event batches to a bucket.
- Admin UI for configuring sinks, testing delivery, and inspecting failures.

### Prometheus Metrics

Relic should expose operational performance data through a Prometheus scrape
endpoint, not by storing per-request timing details in durable event rows.
Activity records answer "what happened"; metrics answer "how is the system performing."

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
- `relic_api_audit_write_duration_seconds{route,operation,status}`

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
- Store high-cardinality identity in audit events, activity records, and logs,
  then correlate via `request_id`.
- Use OpenTelemetry traces later for sampled per-request timing forensics rather
  than persisting every timing breakdown in PostgreSQL.

### Observability and Storage Intelligence

Storage intelligence should be derived after the audit and activity layers
exist, using the durable activity stream plus current canonical tables.

- Folder-level storage usage, file counts, blob counts, and dedupe savings.
- Folder-level placement breakdown by storage tier and backing bucket.
- Bucket latency history and error rates from Prometheus metrics.
- Gateway overhead analysis from gateway and backend duration histograms.
- Latency percentiles by low-cardinality dimensions such as operation, bucket,
  tier, status, and object size band.
- Bucket probe failures and capacity pressure.
- Processor queue health and parser failure rates from Prometheus metrics.
- Per-file processor diagnostics from activity records and canonical metadata.
- Lifecycle movement history, including why a blob moved and which policy drove
  the decision.
- Admin views that explain effective storage policy inheritance for folders.
- Derived rollups maintained incrementally from activity records where that is
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
- Should folder-level stats be computed synchronously, cached, or maintained by
  incremental activity records?
- How much S3 compatibility is required before advertising Relic as an
  S3-compatible gateway?
- Which processors should be required before an activity record is considered
  fully handled, and which should be optional best-effort enrichment?
