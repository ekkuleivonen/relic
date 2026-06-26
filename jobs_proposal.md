# Jobs Proposal

## Direction

Relic should start with hardcoded background job types, not a dynamic job system.

The durable primitive is `job_runs`: records of work Relic has queued, is running, or has completed. The runnable job types live in Go code as constants and handlers. This keeps the first implementation small while still giving Relic durable progress, retries, locking, and UI visibility.

Do not add `jobs` or `job_triggers` tables yet. They may become useful later if Relic supports user-defined jobs, configurable schedules, external workers, or hosted execution. Until then, they create configuration drift without solving a current product problem.

The conceptual split should stay simple:

```text
Job type -> hardcoded kind of work
Handler  -> executable implementation for that type
Run      -> durable execution instance
```

Examples:

```text
sync_bucket
scan_bucket
import_objects
remove_objects
refresh_objects
extract_attributes
detect_duplicates
cleanup_runs
```

## Year 1 Job Types

### `sync_bucket`

Reconcile upstream state into Relic for a whole bucket or a subset.

It can run against:

* A whole bucket.
* A prefix.
* Objects modified since a upstream timestamp filter.

Example input:

```json
{
  "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
  "prefix": "optional/path/",
  "modified_since": "2026-06-01T00:00:00Z"
}
```

This is the heavy planner path for making Relic's catalog match storage. It lists upstream objects, compares that listing with Relic's active catalog, and creates child `job_runs` for the actual mutations:

* `import_objects` for keys that exist upstream but not locally.
* `refresh_objects` for existing keys whose cheap listing evidence changed.
* `remove_objects` for local objects missing from the upstream listing.

`sync_bucket` should not upsert or delete object rows directly. Its result should report object counts and child job IDs so the job trace explains what changed.

### `scan_bucket`

Sample upstream state to detect drift without doing a full reconciliation.

It can run against the same scopes as `sync_bucket`:

* A whole bucket.
* A prefix.
* Objects modified since a upstream timestamp filter.

Example input:

```json
{
  "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
  "prefix": "optional/path/",
  "modified_since": "2026-06-01T00:00:00Z"
}
```

The sample size should scale relative to the known object count within the selected scope. A small scope can be scanned more thoroughly; a very large scope should use a bounded sample. The result should report whether the scope looks healthy, suspicious, or needs a full sync.

This job should avoid broad mutation. It is a detection and confidence job.

### `import_objects`

Import or upsert one or more objects into Relic.

This is the path for upstream create/PUT notifications, targeted imports, and new keys discovered by `sync_bucket`. It should fetch upstream metadata for the specified keys and create or update Relic object rows.

Job input should carry bucket/key/version fields and any cheap evidence already known from a listing or event.

The handler should convert upstream-shaped evidence into Relic's attribute namespaces before writing storage rows. That conversion should live in one reusable, well-tested mapper, not be reimplemented in each handler. If conversion fails, the `import_objects` run should fail visibly and be retried or inspected like any other job failure.

If the input includes a complete enough upstream snapshot, the handler can use it directly and skip a remote metadata read. Otherwise, it should call the upstream to read object metadata, then run the same mapper.

Example input:

```json
{
  "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
  "objects": [
    {
      "key": "photos/a.jpg",
      "version_id": "optional-upstream-version",
      "etag": "\"abc123\"",
      "size": 123456,
      "last_modified": "2026-06-01T00:00:00Z",
      "storage_class": "STANDARD"
    }
  ],
  "source_job_run_id": "jobrun_source"
}
```

### `remove_objects`

Remove one or more objects from Relic.

This is the path for upstream delete notifications and local rows missing from a `sync_bucket` listing. The bytes remain in object storage; this job removes Relic's catalog object because Relic no longer believes that object exists in the bucket.

Example input:

```json
{
  "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
  "objects": [
    {
      "id": "object_0123456789abcdef0123456789abcdef",
      "key": "photos/a.jpg",
      "version_id": "optional-upstream-version"
    }
  ],
  "source_job_run_id": "jobrun_source"
}
```

### `refresh_objects`

Refresh Relic's known metadata or attributes for existing objects.

This can handle upstream metadata changes, tag changes, user-driven attribute refreshes, or changed listing evidence found by `sync_bucket`. The job should support batches because many refreshes will be independent per object. It should HEAD each requested object and update the existing object row with fresh `upstream.*` attributes and provenance.

### `extract_attributes`

Run Relic's opinionated built-in extractor for object attributes.

This should start minimal and practical:

* Content type normalization.
* Content length.
* Image dimensions.
* Media duration where cheap.
* Text/document hints.
* CSV or columnar schema hints.
* Basic keywords or text signals.

Initially, this can run once per object. Later it can rerun when object content changes or when the extractor version changes.

### `detect_duplicates`

Detect duplicate objects and create `duplicate` relationships.

This should start with a cheap candidate pass over matching upstream ETags. ETags are not enough to prove duplication across all upstreams and upload modes, but they are useful for narrowing the search space.

For each matching ETag group, the job should compute a content hash for the candidate objects. If the content hashes match, Relic should create a relationship with type `duplicate` between the matching objects.

This job should not be limited to a single bucket. It should support all catalog objects, selected buckets, or prefix-scoped subsets so Relic can detect duplicates across buckets.

Example input:

```json
{
  "scope": {
    "bucket_ids": [
      "bucket_0123456789abcdef0123456789abcdef",
      "bucket_fedcba9876543210fedcba9876543210"
    ],
    "prefixes": [
      "optional/path/"
    ]
  }
}
```

### `cleanup_runs`

Internal maintenance for stale job state.

This should mark abandoned `running` jobs as failed or cancelled after worker crashes, release stale locks, and eventually clean up old progress/result payloads if they become too large.

## Core Table

### `job_runs`

`job_runs` are durable executions of hardcoded job types.

Suggested fields:

```text
id
type
state
requested_by_type
requested_by_id
target_type
target_id
input jsonb
result jsonb
progress jsonb
attempt
max_attempts
available_at
locked_by
locked_at
started_at
finished_at
error_message
created_at
updated_at
```

Initial states:

```text
pending
running
succeeded
failed
cancelled
```

Example run for syncing a bucket:

```json
{
  "type": "sync_bucket",
  "state": "pending",
  "requested_by_type": "api",
  "target_type": "bucket",
  "target_id": "bucket_0123456789abcdef0123456789abcdef",
  "input": {
    "bucket_id": "bucket_0123456789abcdef0123456789abcdef"
  }
}
```

Example run from a upstream PUT notification:

```json
{
  "type": "import_objects",
  "state": "pending",
  "requested_by_type": "upstream_event",
  "target_type": "bucket",
  "target_id": "bucket_0123456789abcdef0123456789abcdef",
  "input": {
    "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
    "objects": [
      {
        "key": "photos/a.jpg",
        "upstream": "s3",
        "event_name": "ObjectCreated:Put",
        "s3": {
          "bucket": {
            "name": "raw-upstream-bucket-name"
          },
          "object": {
            "key": "photos/a.jpg",
            "eTag": "abc123"
          }
        }
      }
    ]
  }
}
```

## Handler Registry

Handlers should be registered in code.

Conceptual Go shape:

```go
type JobType string

const (
	JobTypeSyncBucket        JobType = "sync_bucket"
	JobTypeImportObjects     JobType = "import_objects"
	JobTypeRemoveObjects     JobType = "remove_objects"
	JobTypeRefreshObjects    JobType = "refresh_objects"

  JobTypeScanBucket        JobType = "scan_bucket"
	JobTypeExtractAttributes JobType = "extract_attributes"
	JobTypeDetectDuplicates  JobType = "detect_duplicates"
	JobTypeCleanupRuns       JobType = "cleanup_runs"
)

type Handler interface {
	Type() storage.JobType
	Handle(ctx context.Context, run storage.JobRun) error
}

type Runner struct {
	Store     *storage.Store
	WorkerID string
	Handlers map[storage.JobType]Handler
}
```

There is no separate permission model for MVP. Handlers are trusted internal code, and normal repository/service boundaries should enforce invariants.

## Queue Architecture

Use Postgres as the job queue for now.

Reasons:

* Job run state must be durable anyway.
* The UI needs to list runs, show detail, and poll progress.
* `FOR UPDATE SKIP LOCKED` supports safe concurrent workers.
* Retry, locking, progress, result, and error state live in one place.
* It keeps executable work durable in Relic-owned storage even when upstream events arrive through JetStream.

Claiming work should happen transactionally:

```sql
SELECT id
FROM job_runs
WHERE state = 'pending'
  AND available_at <= now()
ORDER BY created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Then mark the selected run as `running`, set `locked_by`, `locked_at`, and `started_at` in the same transaction.

Runner loop:

1. Claim the next pending `job_run`.
2. Resolve the handler by `job_runs.type`.
3. Dispatch to the handler.
4. Handler heartbeats progress through the job run repository.
5. On success, mark the run `succeeded`.
6. On failure, increment attempts and either retry later or mark `failed`.
7. On shutdown, stop claiming new runs and let the active run finish or observe context cancellation.

This keeps deployment simple now:

```text
relic api
```

But leaves room for later:

```text
relic api
relic worker
```

Both processes would use the same repositories and claim semantics.

## Bucket Sync Flow

The API should stay thin.

Suggested endpoint:

```http
POST /api/buckets/:id/sync
```

It should:

1. Verify the bucket exists.
2. Create a pending `job_run` with `type = sync_bucket`.
3. Return `202 Accepted` with the run.

It should not scan object storage directly.

The `sync_bucket` handler should:

1. Load the bucket.
2. Decrypt credentials through `secrets.Manager`.
3. Build the upstream adapter from bucket upstream/config.
4. List objects page by page.
5. Load Relic's local object rows for the same scope.
6. Compare upstream listing evidence against local `attributes.upstream`.
7. Create `import_objects`, `refresh_objects`, and `remove_objects` child runs in bounded batches.
8. Update `job_runs.progress`.
9. Mark the run succeeded or failed.

The child handlers own catalog mutations. `import_objects` and `refresh_objects` perform HEAD calls and upsert object attributes/provenance; `remove_objects` performs targeted local deletion.

## Upstream Events

Upstream notifications arrive through platform-provided NATS JetStream. JetStream is durable transport, but Postgres should still be Relic's durable receipt and job state.

Upstream events should flow through a Relic-owned inbox before becoming jobs:

```text
Upstream event
  -> JetStream
  -> upstream_events inbox
  -> batched job_runs
```

The consumer should insert the raw upstream envelope into `upstream_events` before acknowledging the JetStream message. Then a processor can dedupe, coalesce, and batch those events into hardcoded jobs.

Initial mapping:

```text
Upstream PUT    -> import_objects
Upstream DELETE -> remove_objects
Upstream tags   -> refresh_objects
```

These notifications are evidence, not truth. They may be lost, duplicated, delayed, or reordered. `sync_bucket` and `scan_bucket` remain the correctness backstop.

## Job Run Events

`job_runs.progress` and `job_runs.result` are enough for MVP UI state.

Operational debugging may eventually need richer execution history. A future table can capture append-only run events or logs:

```text
job_run_events
  id
  job_run_id
  level
  message
  data jsonb
  created_at
```

This should not block MVP implementation.

## Upstream Boundary

Upstream-specific object storage behavior should stay out of HTTP handlers and storage repositories.

Suggested interface:

```go
type ObjectUpstream interface {
	ListObjects(ctx context.Context, input ListObjectsInput) (ObjectPage, error)
	HeadObject(ctx context.Context, input HeadObjectInput) (ObjectInfo, error)
}
```

The sync/import/refresh handlers should depend on a upstream factory:

```go
type UpstreamFactory interface {
	ForBucket(ctx context.Context, bucket storage.Bucket, credentials []byte) (ObjectUpstream, error)
}
```

An S3-compatible implementation can live under a upstream package, while storage remains responsible only for persisted Relic data.

## JetStream And Postgres

JetStream should not be the source of truth for job runs.

It should complement Postgres:

```text
Postgres = durable truth
JetStream = upstream event transport
```

Good uses for JetStream:

* Carry upstream notifications from the platform.
* Absorb upstream-side bursts before Relic consumes them.
* Replay upstream notifications into Relic's `upstream_events` inbox.
* Publish `job_run.created`, `job_run.progressed`, and `job_run.completed` events.
* Support higher-throughput event-driven import/remove/refresh paths.

If JetStream is down, Relic may stop receiving new upstream events, but Postgres should still contain all accepted upstream events, durable job state, and catalog state. Workers should still be able to poll `job_runs`.

## Implementation Order

Recommended next steps:

1. Add `job_runs` migration.
2. Add object table and repository.
3. Add `JobRunStore` with create, get, list, claim, progress, success, retry, and fail methods.
4. Add `Store.JobRuns()` and transaction variants.
5. Add hardcoded job type constants.
6. Add a small in-process runner with Postgres claiming.
7. Add upstream adapter and `sync_bucket` handler.
8. Add `POST /api/buckets/:id/sync` to create a `sync_bucket` run.
9. Add `GET /api/job-runs` and `GET /api/job-runs/:id` for UI progress.
10. Add `scan_bucket`, `import_objects`, `remove_objects`, `refresh_objects`, `extract_attributes`, `detect_duplicates`, and `cleanup_runs` as the product needs them.
