# Relic Hazard Log

Production-readiness audit across the filesystem, storage, S3 gateway, access
control, search, maintenance, and operational surfaces.

## Findings

### H-001: Permission and access-key revocation can lag behind admin changes

- **Area:** Access control, S3 gateway
- **Impact:** High. A revoked folder grant or access key can remain effective in
  another API/worker process until its in-memory TTL expires, so users may keep
  listing or accessing objects briefly after an admin removes access.
- **Suggested fix or mitigation:** Move hot-path auth/permission caches to Redis
  with explicit invalidation, or version grants/access keys in the database and
  include the version in cache keys. Until then, keep TTLs very short and document
  revocation as eventually consistent.

### H-002: S3 ListObjects cache is not cleared on permission changes

- **Area:** Access control, S3 gateway listings
- **Impact:** High. A user whose access was revoked can receive a cached
  `ListObjectsV2` response for the old permission set until the listing cache
  expires.
- **Suggested fix or mitigation:** Clear the S3 list response cache when folder
  grants are created, updated, or revoked. Include a permission generation value
  in the cache key for multi-process safety.

### H-003: Uploads have no hard product limit

- **Area:** Uploads, S3 gateway, storage guardrails
- **Impact:** High. A user can upload very large objects until backing storage,
  local spooling disk, or bucket capacity fails, causing noisy errors and
  possible service degradation.
- **Suggested fix or mitigation:** Add a configured maximum upload size enforced
  while streaming request bodies and during multipart completion. Return a clear
  S3/API error before exhausting local disk or object-store capacity.

### H-004: Quotas and retention/deletion protection are not implemented

- **Area:** Data safety guardrails
- **Impact:** High. Users can accidentally or maliciously consume unbounded
  storage, and admins cannot protect critical folders from deletion or enforce
  retention/legal-hold rules.
- **Suggested fix or mitigation:** Implement per-user, per-folder, and global
  quotas first, then add retention/deletion-protection checks to file, folder,
  S3 delete, and purge paths.

### H-005: Bucket credentials are returned in admin read responses

- **Area:** Bucket administration
- **Impact:** High. Any admin API response for bucket reads includes decrypted
  `key_id` and `secret_access_key`, increasing blast radius from logs, browser
  inspection, support captures, or compromised admin sessions.
- **Suggested fix or mitigation:** Treat bucket secrets as write-only. Return
  masked key identifiers and expose a rotate/update flow instead of returning the
  decrypted secret.

### H-006: Placement can choose an unprobed or unreachable bucket

- **Area:** Object placement, bucket health
- **Impact:** Medium. New writes can target a bucket with no successful probe
  history if it is the only bucket with capacity, producing user-facing upload
  failures instead of clear operator remediation.
- **Suggested fix or mitigation:** Require at least one recent successful probe
  before a bucket is eligible for new writes, with an admin override for initial
  bootstrap.

### H-007: Multipart completion assembles the whole object through local disk

- **Area:** Multipart uploads, S3 gateway
- **Impact:** Medium. Large multipart uploads are downloaded from temporary
  object parts, reassembled locally, then uploaded again, which can exhaust disk,
  saturate API workers, and make large client uploads unreliable.
- **Suggested fix or mitigation:** Complete multipart uploads with object-store
  multipart copy/compose when available, or stream assembly with strict size and
  disk limits plus a dedicated worker path.

### H-008: Search and facets load all visible candidate files into memory

- **Area:** Search and metadata
- **Impact:** Medium. Large tenants or broad recursive searches can become slow
  or memory-heavy because filtering, sorting, totals, and facets happen over all
  visible `File` rows in Python.
- **Suggested fix or mitigation:** Push filtering, sorting, pagination, and facet
  aggregation into Postgres JSONB/GIN/expression-index queries, and add query
  timeouts or result-window limits.

### H-009: Recursive folder walks scan the full folder table

- **Area:** Filesystem, permissions, search scopes, processors
- **Impact:** Medium. Large folder trees make recursive listings, stats, search
  scopes, and processor folder scopes increasingly expensive and latency-prone.
- **Suggested fix or mitigation:** Use a recursive CTE, closure table, materialized
  path, or cached tree version keyed by database change generation.

### H-010: Prometheus metrics endpoint is missing

- **Area:** Observability
- **Impact:** Medium. Operators cannot alert on request latency, S3 errors,
  queue depth, cursor lag, bucket probe health, or maintenance failures with
  standard scrape-based monitoring.
- **Suggested fix or mitigation:** Ship `/metrics` with low-cardinality gateway,
  API, processor, maintenance, queue, and bucket-probe metrics before production
  rollout.

### H-011: Worker heartbeat state is missing

- **Area:** Processing and maintenance operations
- **Impact:** Medium. `/readyz` reports queue depth and processor registry state,
  but it cannot prove dispatcher, processing worker, or maintenance worker pods
  are alive and making progress.
- **Suggested fix or mitigation:** Add Redis or database heartbeats for dispatcher
  and workers, expose them in readiness/admin UI, and alert when stale.

### H-012: Processor failure handling depends on manual skip/rewind only

- **Area:** Event log and processors
- **Impact:** Medium. A poison event halts a processor cursor until an admin
  intervenes, delaying metadata extraction or future external sinks for every
  later matching event.
- **Suggested fix or mitigation:** Keep manual skip/rewind, but add surfaced
  failure detail, alerting on cursor age/lag, and eventually a bounded
  dead-letter/auto-quarantine path for unreliable external sinks.

### H-013: Import/sync from existing buckets is not available

- **Area:** Import and migration
- **Impact:** Medium. Existing object-store data cannot be brought under Relic
  control without custom tooling, making production adoption risky for teams with
  preexisting buckets.
- **Suggested fix or mitigation:** Add resumable import jobs that preserve object
  keys as folder paths, detect drift, emit file events, and report progress and
  failures.

### H-014: File versioning is not available

- **Area:** Data safety
- **Impact:** Medium. Overwrites replace the logical file reference, so users
  cannot restore previous versions or compare metadata after accidental updates.
- **Suggested fix or mitigation:** Add version rows for overwrite/upload flows,
  restore APIs, retention policy for old versions, and search controls for latest
  versus all versions.

### H-015: Native S3 compatibility coverage is still narrow

- **Area:** S3 gateway compatibility
- **Impact:** Medium. Core boto3 flows are covered, but broader clients may hit
  unsupported behaviors such as virtual-hosted style, streaming SigV4 payloads,
  richer listing edge cases, or client-specific multipart assumptions.
- **Suggested fix or mitigation:** Expand the compatibility harness to AWS CLI,
  rclone, and target lakehouse clients; publish explicitly supported operations
  and fail unsupported ones with stable S3 error codes.

### H-016: Configuration warnings do not fail readiness

- **Area:** Deployment safety
- **Impact:** Low. `/readyz` reports development defaults for secrets as warnings
  but still returns overall OK, so a misconfigured deployment can pass readiness.
- **Suggested fix or mitigation:** Add a production mode that fails readiness on
  default `ENCRYPTION_SECRET`, `SESSION_SECRET`, `REDIS_PASSWORD`, admin password,
  or signing-key settings.

