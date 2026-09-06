# 0007: Job run traces

Date: 2026-06-28

## Status

Accepted

## Context

Pithosys's core action is syncing a bucket: list upstream, compare with the local catalog, and apply import, refresh, and remove mutations. Today this is implemented as a tree of `job_runs`:

```text
sync_bucket
  ├── import_objects (many batches)
  ├── refresh_objects
  └── remove_objects
```

`scan_bucket` can enqueue scoped `sync_bucket` children. Upstream events enqueue standalone `import_objects` runs. All of these share the same execution model: claim a row, run a handler, update `progress`, succeed or fail.

Two problems make sync progress hard to understand:

1. **Lifecycle mismatch.** A fan-out handler enqueues child jobs and returns. The runner marks the parent `succeeded` immediately, even though most catalog work has not run yet. The user sees "sync succeeded" while the object catalog is still empty.

2. **No correlation key.** Child jobs link to their parent via `requested_by_id`, but there is no first-class identifier for the whole operation. Aggregating progress across a deep tree requires ad hoc walks. The UI falls back to raw `progress` jsonb (`listed, 4000 objects seen`) on individual rows.

We considered separate tables (`sync_operations`, `job_run_progress` spans) but rejected them. They duplicate lifecycle state that already belongs on `job_runs` and risk making sync a special domain. Pithosys is greenfield with no backwards-compatibility constraints.

We need a generic way to group job runs into one user-visible operation, keep the root job honest about completion, and expose a simple progress read model for the UI — without deviating from the established job execution patterns.

## Decision

### Trace and span model

Add `trace_id` to `job_runs`:

```sql
ALTER TABLE job_runs ADD COLUMN trace_id text NOT NULL;
CREATE INDEX job_runs_trace_id_idx ON job_runs (trace_id);
CREATE INDEX job_runs_trace_active_idx ON job_runs (trace_id)
    WHERE state IN ('pending', 'running');
```

Each `job_runs` row is a **span**: one claimable unit of work. No separate `span_id` column — **`job_run.id` is the span identifier.**

Tree structure uses existing provenance fields:

| Concept | Field |
| --- | --- |
| Trace (whole operation) | `trace_id` |
| Span (one job) | `id` |
| Parent span | `requested_by_id` (when `requested_by_type = 'job'`) |

**Root job:** the row where `id = trace_id`.

### Trace assignment

On `CreateJobRun`:

1. **New operation** (no job parent): set `trace_id = id`.
2. **Child job** (`requested_by_type = 'job'`): set `trace_id = parent.trace_id`.
3. **Explicit trace** (optional API param): set `trace_id` to the supplied value. Used when an external caller wants to correlate work; default is automatic.

Examples:

| Trigger | Root job | `trace_id` |
| --- | --- | --- |
| User clicks Sync | `sync_bucket` | `id` |
| Scan scheduler | `scan_bucket` | `id` |
| Scan enqueues scoped sync | `sync_bucket` child | same as scan's `trace_id` |
| Upstream event | `import_objects` | `id` (single-span trace) |

### Fan-out jobs await their trace

When a handler returns a result containing `child_job_ids`, the runner **does not** mark that job `succeeded`. The job stays `running` until the trace completes.

A **trace completion pass** (part of the runner loop or supervisor tick) runs for each `running` job where `id = trace_id`:

1. Load all rows with the same `trace_id`.
2. If any are `pending` or `running`, update the root's `progress` rollup and stop.
3. If all are terminal, aggregate child `result` counters into the root's `progress` and `result`, then succeed or fail the root based on child outcomes.

Failure policy: if any child job in the trace is `failed` and will not retry, the root job fails with a summary error. Individual child errors remain on their rows for debugging.

This applies to all fan-out job types (`sync_bucket`, `scan_bucket` when it enqueues sync children, and any future composite jobs). Sync is not special; it is the deepest fan-out tree today.

### Progress on the root span

The root job's `progress` jsonb is the **UI contract** for the whole trace. It is updated:

- **During root handler execution** — phase-local counters (e.g. listing).
- **By the trace completion pass** — rollup from descendant spans.

Standard phases for `sync_bucket`:

| Phase | Meaning |
| --- | --- |
| `listing` | Paginating upstream; `objects_listed` increments |
| `planning` | Comparing upstream listing with local catalog |
| `importing` | Child `import_objects` spans running |
| `refreshing` | Child `refresh_objects` spans running |
| `removing` | Child `remove_objects` spans running |

Example root `progress` during import:

```json
{
  "phase": "importing",
  "objects_listed": 248312,
  "objects_planned": { "import": 248312, "refresh": 0, "remove": 0 },
  "objects_applied": { "imported": 41200, "refreshed": 0, "removed": 0 },
  "batches": { "import": { "done": 412, "total": 2483, "failed": 0 } }
}
```

Child jobs keep their own `progress` for batch-level detail (`objects_total`, `objects_headed`, `objects_upserted`). The bucket page reads the root row only.

Phases within a single long-running job (e.g. listing pages) are **progress updates on that span**, not separate job rows.

### Active trace detection

A trace is active when any row with its `trace_id` is `pending` or `running`:

```sql
SELECT EXISTS (
  SELECT 1 FROM job_runs
  WHERE trace_id = $1
    AND state IN ('pending', 'running')
);
```

Use this to:

- Disable the Sync button while a bucket sync trace is active.
- Dedupe scheduler enqueues (`HasActiveJobRun` extends to trace-aware checks where needed).

For bucket-scoped queries, filter by `target_type`, `target_id`, and root job `type`, then inspect the trace.

### API

No bucket-specific progress endpoint. Extend the existing jobs API:

```http
GET /api/job-runs?trace_id=:id
```

Returns all spans in the trace, ordered by `created_at`.

```http
GET /api/job-runs/:id?include=trace_summary
```

When `:id` is a root span (`id = trace_id`), the response includes a computed rollup: trace state, phase, counters, `stale_seconds` (derived from root `updated_at`), and child counts by type and state.

List filters (`target_type`, `target_id`, `type`) are unchanged. The bucket page loads the latest root `sync_bucket` for the bucket, then reads its trace summary.

### UI

The **bucket detail page** is the primary sync progress surface:

- Show a sync status card when the latest trace for the bucket is active or recently failed.
- Poll the root job (with `include=trace_summary`) every 3 seconds while active.
- Map `progress.phase` to plain language and show a determinate progress bar only when planned counts are known (importing and later phases).
- During listing, show `objects_listed` with an indeterminate bar. Warn when `stale_seconds` exceeds a threshold.

Job run detail and observability pages reuse the same progress formatter and trace summary. Child span lists are for debugging, not the primary user story.

### Large bucket listing

Trace semantics do not change the listing algorithm, but the root `sync_bucket` handler supports resumable streaming sync for large buckets:

- Persist `listing_checkpoint` in root `progress` after each upstream page.
- Resume from checkpoint on retry instead of restarting the trace.
- Process each listing page incrementally: diff against local catalog rows for that page, enqueue import/refresh child jobs immediately, and record seen upstream keys in generic `job_spill`.
- After listing completes, stream local catalog rows missing from `job_spill` to plan remove jobs, then delete spill rows for the sync job run.

`job_spill` is a generic handler spill table keyed by `(job_run_id, spill_key)` and is not sync-specific. Other long-running jobs may use it later if needed.

## Consequences

- One column (`trace_id`) correlates an entire operation without a parallel progress domain.
- Each job row remains a span; `requested_by_id` remains the parent link. No new special cases for sync.
- Root jobs stay `running` until the trace completes, aligning job state with user expectations.
- The bucket page can show honest sync progress from a single polled root row.
- `GET /job-runs?trace_id=` provides a generic debug view for any composite job.
- Fan-out handlers and the runner must be updated: return `child_job_ids`, defer root completion, run the trace completion pass.
- `CreateJobRun` must set `trace_id` on every insert; existing code paths that create child jobs inherit automatically.
- `jobs_proposal.md` should be updated: step "mark succeeded" applies when the trace completes, not when children are enqueued.
- Over-granular spans (per upstream page, per HEAD call) are explicitly discouraged. Spans are job boundaries; phase counters live in `progress`.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| `sync_operations` table | Duplicates `job_runs` lifecycle; makes sync a special domain |
| `job_run_progress` span table | Dual write model; job rows already map to spans |
| `root_job_run_id` only | Equivalent to `trace_id` with less familiar vocabulary; `trace_id` was chosen |
| Separate `span_id` column | Redundant when `job_run.id` is the span identifier |
| Parent `progress` only, no trace completion pass | Does not fix root job succeeding before children finish |
| Client-side aggregation of child jobs | Does not scale to thousands of import batches; wrong layer |
