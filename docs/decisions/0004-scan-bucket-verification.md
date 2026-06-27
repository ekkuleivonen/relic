# ADR 0004: Scan Bucket Verification

## Status

Accepted

## Context

Relic needs a background job that detects catalog drift against upstream object storage without performing a full reconciliation on every run.

The jobs proposal defines two related job types:

* **`sync_bucket`** — list upstream, compare with the local catalog, and enqueue child `import_objects`, `refresh_objects`, and `remove_objects` runs. This is the heavy correctness path.
* **`scan_bucket`** — sample upstream state, estimate whether the catalog matches storage, and avoid broad mutation. This is the detection and confidence path.

`sync_bucket` is implemented today. It performs a full upstream listing for the bucket scope, compares listing evidence against local `upstream.*` attributes, and creates child mutation jobs. It does not yet accept per-run scope overrides such as `prefix` from job input.

Relic's portable S3-compatible upstream boundary exposes only `ListObjects` and `HeadObject`. There is **no standard S3 API** for bucket-level object count or total bytes. Portable totals require enumerating objects and summing listing results. Provider-specific metrics such as AWS CloudWatch exist but are delayed, approximate, and not available across MinIO, R2, Wasabi, and other compatible backends.

Because of that limitation, bucket-level upstream aggregate checks are a poor foundation for `scan_bucket`. They would either require a full upstream listing — the same cost as `sync_bucket` — or couple Relic to non-portable provider APIs outside the current `packages/upstreams/s3compat` contract.

Relic still needs a bounded-cost verification path. The architectural answer is to operate over **verification partitions**: disjoint slices of the scan scope that can be sampled, fingerprinted, and escalated separately. Escalation remains scoped `sync_bucket`; the scan handler itself never mutates the catalog.

### Why not key-root partitioning

A tempting first approach is to partition by first path segment (`photos/`, `logs/`, `/`). That maps cleanly to S3 prefix listing, but it makes verification cost **dependent on how users organize their buckets** — something Relic does not control.

Production buckets frequently concentrate objects under a single prefix:

```text
photos/      250M objects
videos/       40M objects
```

```text
logs/        800M objects
```

```text
objects/       2B objects
```

With key-root partitioning, selecting one of these partitions requires listing hundreds of millions of objects. At that point the scan has effectively become a full reconciliation, defeating its primary purpose.

There is no upper bound on key-root partition size. Sampling cannot fix this when a single partition dominates the bucket. A run-level cost budget can stop the work, but it cannot make verification predictable — it only makes it incomplete.

**Verification cost must be determined by Relic's partitioning strategy, not by user-defined key layout.**

## Decision

Relic will implement `scan_bucket` as a **read-only verification job** over sampled **verification partitions**.

The handler will:

1. Resolve scan scope from job input and bucket configuration.
2. Assign objects to disjoint verification partitions within that scope.
3. Sample a subset of partitions.
4. For each sampled partition, compare local and upstream fingerprints.
5. Stop fingerprint evaluation for a partition as soon as drift is proven.
6. On mismatch, enqueue a child **`sync_bucket`** run scoped to that partition. The scan handler must not mutate catalog rows or enqueue `import_objects`, `refresh_objects`, or `remove_objects` directly.
7. Stop scanning when a run-level cost budget is exhausted. Remaining partitions may be checked on future runs.

### Relationship to `sync_bucket`

| | `scan_bucket` | `sync_bucket` |
| --- | --- | --- |
| Purpose | Detect likely drift | Reconcile catalog with upstream |
| Upstream work | One paginated listing pass over scope, routed into partition accumulators; bounded by run budget | Full listing for scope |
| Catalog writes | None | Via child mutation jobs |
| Output | Status + scanned/mismatched partitions + child sync job IDs | Planned mutation counts + child job IDs |

`scan_bucket` is a backstop alongside event-driven import/remove/refresh paths. A clean scan does not prove global correctness. It raises or lowers confidence and localizes where a full sync is needed.

### Verification partitions

A **verification partition** is a disjoint slice of the scan scope that Relic can fingerprint independently of other partitions.

The scan pipeline is defined in terms of partitions, not a specific partitioning scheme:

```text
assign partitions → sample partitions → fingerprint(partition) → escalate mismatches
```

How partitions are assigned is an implementation choice, but the scheme must satisfy one architectural requirement:

**If verification becomes too expensive, Relic must be able to reduce per-partition cost by increasing partition count — without requiring users to reorganize their buckets.**

Schemes that satisfy this include:

* **Hash-based partitions** — e.g. `hash(key) % N`. Objects are evenly distributed regardless of prefix layout; increasing `N` immediately reduces expected partition size.
* **Adaptive partitions** — split a partition once it exceeds a size threshold, producing predictable scan costs even when hash variance or scope skew leaves individual shards large.
* **Fixed-range hash partitions** — contiguous ranges over a hash space (similar to database shard ranges or consistent hashing). Verification cost is controlled by range width rather than user prefixes.

Schemes that do **not** satisfy this requirement include key-root, prefix-tree, or any partition boundary derived from user-chosen path segments. Those may appear as optional plugin strategies later, but they are not acceptable as the default or initial implementation.

#### Initial partition strategy: hash-based sharding

The v1 partitioner assigns every object key in scope to one of `N` fixed partitions:

```text
partition_index = hash(key) % N
```

Where:

* `hash` is a stable, portable function over the full object key (implementation detail; must be consistent between local catalog queries and upstream listing routing).
* `N` is a Relic-controlled partition count, not derived from bucket layout. Start with a sensible default (e.g. 256 or 1024) and tune operationally.
* Partition identifiers are logical — e.g. `"042/256"` — not S3 prefixes.

Properties:

* Expected partition size is approximately `objects_in_scope / N`, independent of whether those objects live under `photos/`, `objects/`, or flat keys.
* Increasing `N` reduces per-partition work. This is the primary cost knob.
* Partitions are always disjoint and cover the full key space within scope.
* The partition set is known upfront (`0 .. N-1`). No catalog discovery step is required to learn partition boundaries.

Local catalog filter for partition `i`:

```sql
-- illustrative; exact hash expression is an implementation detail
WHERE bucket_id = $1
  AND key LIKE $scope_prefix || '%'
  AND mod(hash(key), $N) = $i
```

Upstream routing uses the same hash during a paginated `ListObjects` pass over the effective scope prefix. S3 cannot filter by hash server-side, so upstream partition evidence is built by routing each listed object into the appropriate partition accumulator during the listing pass.

**Single listing pass.** The scan handler performs one paginated upstream listing over scope per run. Each listed object updates fingerprint accumulators for its hash partition. After the pass (or when the run budget is exhausted), sampled partitions are compared. Do not perform a separate upstream listing per sampled partition — that would multiply cost by sample size.

Future implementations may add adaptive sub-splitting when a hash partition still exceeds a configured object threshold during a run. That is not required for v1.

### Sampling

Sampling applies to the fixed partition set `{0 .. N-1}`, not to individual object keys.

Ship with fixed defaults based on local object count in scope:

| Local object count in scope | Sample rate |
| --- | --- |
| Large (> 100,000) | 1% of partitions |
| Medium (10,000–100,000) | 10% of partitions |
| Small (< 10,000) | 25% of partitions |

Small scopes may scan all partitions when `N` is already modest relative to object count.

Do not expose sample-rate overrides, threshold overrides, or bucket-plugin tuning in the first implementation. Add configuration only after operational experience shows which parameters need it.

Sampling must be **deterministic and rotating**:

* Use a stable hash of the partition identifier (e.g. `"042/256"`).
* Combine it with a time-based epoch such as daily or weekly so retries within an epoch are reproducible while coverage rotates over time.

Do not use nondeterministic randomness. Do not key sampling only to a single run ID, which makes retries non-reproducible across executions.

Skip empty partitions: if both local and upstream accumulators show zero objects for a sampled partition, treat it as healthy without further work.

### Fingerprints

For each sampled partition, Relic compares:

```text
fingerprint(local) == fingerprint(upstream)
```

The fingerprint algorithm is an **implementation detail**. The ADR does not prescribe count, bytes, ETag digests, or other specific fields. Today's implementation may use cheap aggregates followed by stronger checks; tomorrow's may use a different strategy without revising this ADR.

Requirements on the fingerprint abstraction:

* Both sides must use listing evidence comparable to what `sync_bucket` relies on.
* Comparison must short-circuit. Once drift is proven for a partition, stop further fingerprint work and escalate immediately.
* Fingerprints are confidence signals, not content proofs.

Example short-circuit flow:

```text
count differs → mismatch → enqueue scoped sync
bytes differ  → mismatch → enqueue scoped sync
stronger fingerprint differs → mismatch → enqueue scoped sync
all checks pass → partition healthy
```

Do not compute expensive fingerprint steps after an earlier step has already established mismatch.

### Scan cost budget

Every `scan_bucket` run must enforce a cost budget. The scan stops when the budget is exhausted and may resume remaining partitions on future runs.

The budget may be expressed through implementation limits such as:

* maximum objects listed upstream during the listing pass
* maximum bytes accounted for during listing
* maximum scan duration

Exact limits are implementation details. The architectural requirement is predictable operational cost.

Hash partitioning makes per-partition size predictable in expectation, but a single listing pass over a large scope can still be expensive. The budget caps total upstream work per run regardless of partition scheme.

### Correctness limitations and blind spots

Consumers of scan results must understand exactly what is and is not verified.

**Sampling blind spot.** Unsampled partitions are not checked on that run. A `healthy` result means all **sampled** partitions matched, not that the entire bucket is correct.

**Listing-pass blind spot.** Upstream partition accumulators are only as complete as the listing pass before the budget stops. If the budget is exhausted mid-pass, upstream fingerprints for partitions not yet fully covered must not be treated as complete. Do not report `healthy` when the listing pass did not finish and sampled partitions lack complete upstream evidence.

**Compensating drift blind spot.** Aggregate fingerprint equality does not guarantee per-key correctness. Compensating add/remove pairs within a partition may preserve some aggregate signals while individual keys differ. Escalation to scoped `sync_bucket` is how Relic resolves confirmed partition mismatches precisely.

**Hash collision blind spot.** Keys in different prefixes that share a hash partition are verified together. A mismatch localizes drift to a partition, not to a user-visible prefix. Escalation and operational tooling must describe partition scope in Relic terms (`042/256`), not assume a single directory caused the drift.

Future enhancements may add optional prefix-aware partition strategies for operators who want directory-local verification. Those are not required for v1 and must not become the default.

### Escalation

When a sampled partition mismatches, `scan_bucket` creates a child `sync_bucket` job scoped to that hash partition:

```json
{
  "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
  "scope_prefix": "optional/path/",
  "partition": {
    "scheme": "hash",
    "modulus": 256,
    "index": 42
  },
  "source_job_run_id": "jobrun_scan"
}
```

The exact field names are implementation details. The semantics are not:

* `sync_bucket` must reconcile only keys in scope where `hash(key) % modulus == index`.
* Both local catalog queries and upstream listing for the child run must apply the same partition filter.
* `scan_bucket` must not auto-sync unsampled partitions on a clean sample.

The subsequent `sync_bucket` run is responsible for identifying precise per-key differences within the partition.

Optional job-input `prefix` scopes both the scan and any escalated sync to a subtree. Partition hashing applies to keys within that effective scope, not the whole bucket.

### Job input

Initial `scan_bucket` input is minimal:

```json
{
  "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
  "prefix": "optional/path/"
}
```

Optional scope fields such as `modified_since` may be added later. S3 listing APIs do not provide a portable server-side modified-time filter, so prefix-scoped scans are sufficient for v1.

Do not expose sample-rate, partition-count, or fingerprint tuning through job input in the first implementation.

### Job result

Keep scan results small. Callers need to know:

* which partitions were scanned
* which partitions mismatched
* which scoped sync jobs were scheduled

Example:

```json
{
  "phase": "completed",
  "bucket_id": "bucket_0123456789abcdef0123456789abcdef",
  "scope": {
    "prefix": "raw/"
  },
  "partition_modulus": 256,
  "partitions_sampled": 13,
  "partitions_scanned": 13,
  "partitions_mismatched": ["042/256"],
  "status": "needs_sync",
  "listing_pass_complete": true,
  "child_job_ids": {
    "sync_bucket": ["jobrun_sync_1"]
  }
}
```

Status values for v1:

| Status | Meaning |
| --- | --- |
| `healthy` | All scanned partitions matched and the listing pass completed for scope |
| `needs_sync` | One or more scanned partitions mismatched and scoped sync jobs were enqueued |

Do not introduce additional statuses such as `suspicious` until there is a concrete behavioral difference.

If the cost budget is exhausted before the listing pass completes, or before all sampled partitions are evaluated, the result should reflect partial progress and must not be reported as `healthy`.

### Progress

Heartbeats should use coarse phases such as:

```text
sampling_partitions → listing_upstream → evaluating → escalating
```

## Consequences

This gives Relic:

* A portable drift-detection path that works through the existing S3-compatible list API.
* Clear separation between detection (`scan_bucket`) and reconciliation (`sync_bucket`).
* A partition abstraction that can evolve without rewriting the scan pipeline.
* Predictable operational cost: partition size is controlled by Relic's `N`, not user key layout.
* Actionable escalation: mismatches become partition-scoped `sync_bucket` runs instead of whole-bucket syncs.

This also costs Relic:

* `sync_bucket` must gain partition-scoped input semantics (hash filter) before scan escalation is fully useful.
* Storage needs efficient partition-scoped object queries (hash predicate over keys in scope).
* Shared listing-evidence comparison helpers should be extracted so `sync_bucket` and `scan_bucket` stay aligned.
* Scan results require careful product communication because verification is sampled, not exhaustive.
* Upstream verification requires a full scoped listing pass routed into partition accumulators; savings come from sampling and avoiding mutation work on healthy partitions, not from avoiding listing entirely.

## Package boundaries

`packages/storage` owns:

* Partition-scoped object queries for the v1 hash partitioner
* Job run creation for scan and child sync runs

`packages/upstreams/s3compat` owns:

* Paginated prefix listing
* Listing evidence shapes consumed by fingerprinting

`apps/worker/internal/jobs/scan_bucket` owns:

* Scan orchestration, partition sampling, upstream listing pass with hash routing, fingerprint comparison, budget enforcement, and child `sync_bucket` enqueue

`apps/worker/internal/jobs/sync_bucket` owns:

* Scope reconciliation and child mutation job planning, including partition-scoped runs when escalated from scan

Partition assignment and fingerprint construction should live behind small interfaces so future strategies (adaptive splitting, fixed-range shards, optional plugin partitioners) can replace or extend the v1 hash partitioner without changing the scan handler's core flow.

Shared listing-evidence comparison logic should live in a reusable worker jobs helper or small shared package rather than being duplicated across handlers.

`apps/api` owns:

* `POST /api/buckets/:id/scan` to enqueue a `scan_bucket` run

## Rules

* Do not rely on bucket-level upstream object count or total bytes through the portable S3 object API.
* Do not mutate catalog rows inside `scan_bucket`.
* Do not enqueue `import_objects`, `refresh_objects`, or `remove_objects` directly from `scan_bucket`; escalate to scoped `sync_bucket`.
* Do not use key-root or other user-layout-derived partition boundaries as the default or initial partition strategy.
* Choose partition schemes where increasing partition count reduces per-partition cost without requiring bucket reorganization.
* Keep partitions disjoint and covering the full scope key space.
* Compare fingerprints through a single abstraction; keep the algorithm swappable.
* Short-circuit fingerprint evaluation once drift is proven.
* Build upstream partition evidence in a single listing pass; route objects into partition accumulators by hash.
* Enforce a per-run scan cost budget.
* Use deterministic, epoch-rotated partition sampling.
* Keep v1 configuration to sensible defaults.
* Keep scan result payloads small.
* Document scan blind spots explicitly: sampling, incomplete listing passes, compensating drift, and hash-partition localization.

## Relationship to prior decisions

This ADR **extends** the jobs proposal and the existing `sync_bucket` implementation. It does not change catalog write ownership from ADR 0003: only upstream catalog jobs mutate `upstream.*` attributes, and `scan_bucket` is not one of them.

## Initial implementation order

1. Define the hash partitioner interface and v1 defaults (`N`, hash function, partition ID format).
2. Add storage helpers for partition-scoped object queries and local fingerprint aggregation.
3. Extract shared listing-evidence comparison helpers from `sync_bucket`.
4. Add partition-scoped input handling to `sync_bucket` (hash filter over scope).
5. Implement `scan_bucket` handler with partition sampling, single-pass upstream listing with hash routing, fingerprint comparison, short-circuiting, budget enforcement, and partition-scoped sync escalation.
6. Add `POST /api/buckets/:id/scan`.
7. Add scheduled scans once operational defaults prove sufficient.
