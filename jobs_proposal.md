# Jobs Proposal

## Direction

Relic should use as few work primitives as possible:

* `jobs` define work Relic can perform.
* `job_triggers` define why or when a job should run.
* `job_runs` record executions of those jobs.
* A bucket sync is just a seeded system job.
* Manual bucket sync is just an event that matches a seeded trigger for that job.
* Future plugins should be modeled as jobs.
* Future workflows should not become a separate primitive until there is clear pressure for one. They may be jobs plus configured triggers.

This keeps Relic dogfooding its own primitive layer instead of creating one-off subsystems for sync, plugins, imports, workflows, schedules, webhooks, and maintenance.

The conceptual split should stay clear:

```text
Handler -> executable implementation
Job     -> configured unit of work
Trigger -> event listener that creates runs
Run     -> execution instance
```

A handler is code, such as `sync_bucket`, `delete_objects`, or `verify_duplicates`.

A job is a durable configured invocation of a handler, such as "Sync bucket", "Nightly bucket verification", or "Refresh media metadata".

A trigger describes which events should create a run.

A run records one execution produced by a trigger.

## Core Tables

### `jobs`

`jobs` are durable definitions of work.

Suggested fields:

```text
id
name
description
kind
handler
enabled
config jsonb
created_at
updated_at
```

Example seeded system job:

```json
{
  "id": "job_sync_bucket",
  "name": "Sync bucket",
  "kind": "system",
  "handler": "sync_bucket",
  "enabled": true,
  "config": {}
}
```

`handler` is an internal stable identifier that the runner maps to code. The product can say "Sync bucket", but the primitive is still "run a job".

Multiple jobs may use the same handler with different names, enabled states, and config. A job's handler should be immutable after creation so seeded data, historical runs, and handler-specific config cannot drift into edge cases.

### `job_triggers`

`job_triggers` are durable event listeners that create runs.

Suggested fields:

```text
id
job_id
enabled
config jsonb
created_at
updated_at
```

Trigger config should describe the event types and filters that produce a run. Manual actions, schedules, webhooks, and internal system requests should all enter the same path by emitting events:

```text
Relic:JobManuallyRequested
Relic:ScheduleDue
Relic:WebhookReceived
Relic:SystemMaintenanceRequested
Provider:ObjectCreated
Relic:BucketCredentialsRotated
```

For the MVP, only `Relic:JobManuallyRequested` needs to work.

Example seeded trigger for manual bucket sync:

```json
{
  "id": "trigger_sync_bucket_manual",
  "job_id": "job_sync_bucket",
  "enabled": true,
  "config": {
    "event_types": [
      "Relic:JobManuallyRequested"
    ],
    "payload": {
      "job_id": "job_sync_bucket"
    }
  }
}
```

Manual UI/API actions should not be special-cased as a separate concept. A button click emits `Relic:JobManuallyRequested`; the matching `job_trigger` creates the `job_run`.

Triggers should use flattened event type strings. The event namespace describes what happened.

Provider events are raw signals from storage systems:

```text
Provider:ObjectCreated
Provider:ObjectRemoved
Provider:ObjectTagging
Provider:ObjectRestore
Provider:ObjectAclUpdated
```

These are evidence, not truth. They may be lost, duplicated, delayed, or reordered.

Relic events are emitted after Relic updates its own catalog:

```text
Relic:ObjectDiscovered
Relic:ObjectCreated
Relic:ObjectUpdated
Relic:ObjectDeleted
Relic:ObjectRestored

Relic:AttributeAdded
Relic:AttributeChanged
Relic:AttributeRemoved

Relic:RelationCreated
Relic:RelationDeleted

Relic:CollectionCreated
Relic:CollectionUpdated
Relic:CollectionDeleted

Relic:BucketCreated
Relic:BucketUpdated
Relic:BucketDeleted
Relic:BucketCredentialsRotated

Relic:JobRunCreated
Relic:JobRunStarted
Relic:JobRunSucceeded
Relic:JobRunFailed
Relic:JobRunCancelled

Relic:JobCreated
Relic:JobUpdated
Relic:JobDeleted
Relic:JobEnabled
Relic:JobDisabled

Relic:JobTriggerCreated
Relic:JobTriggerUpdated
Relic:JobTriggerDeleted
Relic:JobTriggerEnabled
Relic:JobTriggerDisabled

Relic:BucketSyncStarted
Relic:BucketSyncCompleted
Relic:BucketSyncFailed
```

These represent changes to Relic's understanding. Most user automation should react to Relic events, while internal maintenance jobs may react directly to provider events.

REST actions that mutate Relic state should emit Relic events too. A user creating a bucket through `POST /api/buckets` should produce `Relic:BucketCreated`; editing endpoint metadata should produce `Relic:BucketUpdated`; rotating credentials should produce `Relic:BucketCredentialsRotated`. The source of a change should not decide whether an event exists.

Trigger config should filter by event type and, where relevant, event payload fields. Attribute-related triggers should support path filtering because metadata changes are central to Relic. Example trigger config:

```json
{
  "event_types": [
    "Relic:AttributeAdded",
    "Relic:AttributeChanged"
  ],
  "attribute_paths": [
    "plugin.duplicate_detection.verified_duplicate"
  ]
}
```

Triggers should support event type and payload filtering from the start of their implementation. Without filtering, imports and job runs could generate too much trigger volume.

### `job_runs`

`job_runs` are durable executions of jobs.

Suggested fields:

```text
id
job_id
trigger_id
trigger_event_type
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
  "job_id": "job_sync_bucket",
  "trigger_id": "trigger_sync_bucket_manual",
  "trigger_event_type": "Relic:JobManuallyRequested",
  "state": "pending",
  "requested_by_type": "api",
  "target_type": "bucket",
  "target_id": "bucket_0123456789abcdef0123456789abcdef",
  "input": {
    "bucket_id": "bucket_0123456789abcdef0123456789abcdef"
  }
}
```

`trigger_event_type` is intentionally denormalized into `job_runs` so historical runs remain understandable if a trigger row changes later.

## Handler Permissions

For the MVP, jobs do not need a separate permission model.

Handlers are trusted internal code. The handler implementation defines which resources it reads or writes, and normal repository/service boundaries should enforce invariants. Adding persisted permissions now would create another source of drift without providing meaningful isolation.

If Relic later supports less-trusted execution, handlers can declare required permissions in code and the runner can enforce them before execution. Avoid adding that layer until there is real pressure from:

* User-defined jobs.
* External execution.
* Multi-tenant environments.
* Hosted Relic.

## Queue Architecture

Use Postgres as the job queue for now.

Reasons:

* Job run state must be durable anyway.
* The UI needs to list runs, show detail, and poll progress.
* `FOR UPDATE SKIP LOCKED` supports safe concurrent workers.
* Retry, locking, progress, result, and error state live in one place.
* It avoids adding NATS before there is a clear need for event fanout or high-throughput streams.

Claiming work should happen transactionally:

```sql
SELECT id
FROM job_runs
WHERE state = 'pending'
  AND available_at <= now()
ORDER BY priority DESC, created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Then mark the selected run as `running`, set `locked_by`, `locked_at`, and `started_at` in the same transaction.

## Runner Shape

The runner can be in-process for the MVP, but it should be structured as if it could move into a separate worker binary later.

Conceptual Go shape:

```go
type Handler interface {
	Type() storage.JobHandler
	Handle(ctx context.Context, run storage.JobRun) error
}

type Runner struct {
	Store     *storage.Store
	WorkerID string
	Handlers map[storage.JobHandler]Handler
}
```

Runner loop:

1. Claim the next pending `job_run`.
2. Load the corresponding `job` definition.
3. Resolve the job's handler.
4. Dispatch to the handler.
5. Handler heartbeats progress through the job run repository.
6. On success, mark the run `succeeded`.
7. On failure, increment attempts and either retry later or mark `failed`.
8. On shutdown, stop claiming new runs and let the active run finish or observe context cancellation.

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
2. Emit `Relic:JobManuallyRequested` with the bucket target.
3. Evaluate matching enabled triggers for `job_sync_bucket`.
4. Create a `job_run` for the matching trigger.
5. Return `202 Accepted` with the run.

It should not scan object storage directly.

The `sync_bucket` handler should:

1. Load the bucket.
2. Decrypt credentials through `secrets.Manager`.
3. Build the provider adapter from bucket provider/config.
4. List objects page by page.
5. Upsert objects in batches.
6. Update `job_runs.progress`.
7. Mark previously-seen missing objects as deleted for a full sync.
8. Mark the run succeeded or failed.

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

Example messages:

```text
started sync
processed page 100
retrying provider request
found duplicate candidate
completed reconciliation
```

This should not block MVP implementation, but the job model should leave room for it.

## Provider Boundary

Provider-specific object storage behavior should stay out of HTTP handlers and storage repositories.

Suggested interface:

```go
type ObjectProvider interface {
	ListObjects(ctx context.Context, input ListObjectsInput) (ObjectPage, error)
}
```

The sync handler should depend on a provider factory:

```go
type ProviderFactory interface {
	ForBucket(ctx context.Context, bucket storage.Bucket, credentials []byte) (ObjectProvider, error)
}
```

An S3-compatible implementation can live under a provider package, while storage remains responsible only for persisted Relic data.

## NATS Later

NATS should not be the source of truth for job runs.

If introduced later, it should complement Postgres:

```text
Postgres = durable truth
NATS = notification and event transport
```

Good future uses for NATS:

* Wake workers when a job run is created.
* Wake trigger evaluators when new events are ready.
* Publish `job_run.created`, `job_run.progressed`, and `job_run.completed` events.
* Fan out `Provider:*` and `Relic:*` events to realtime consumers.
* Support higher-throughput event-driven sync paths.

If NATS is down, Postgres should still contain all durable job state and workers should still be able to poll.

## Implementation Order

Recommended next steps:

1. Add `jobs`, `job_triggers`, and `job_runs` migrations.
2. Seed `job_sync_bucket`.
3. Seed `trigger_sync_bucket_manual` for `Relic:JobManuallyRequested`.
4. Add `JobStore`, `JobTriggerStore`, and `JobRunStore` repositories with tests.
5. Add `Store.Jobs()`, `Store.JobTriggers()`, `Store.JobRuns()`, and transaction variants.
6. Add a small in-process runner with Postgres claiming.
7. Add trigger evaluation for `Relic:JobManuallyRequested`.
8. Add object table and repository.
9. Add provider adapter and `sync_bucket` handler.
10. Add `POST /api/buckets/:id/sync` to emit a manual job request event and return the created run.
11. Add `GET /api/job-runs` and `GET /api/job-runs/:id` for UI progress.
12. Later, expand trigger evaluation for flattened `Provider:*` and `Relic:*` event types.

