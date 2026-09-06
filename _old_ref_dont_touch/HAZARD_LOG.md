# Pithosys Hazard Log

Production-readiness hazards across the filesystem, storage, S3 gateway, access
control, search, maintenance, and operational surfaces.

**Last reviewed:** 2026-05-20 (aligned with P0–P2 app hardening in tree).

## Summary

| ID | Hazard | Status |
| --- | --- | --- |
| H-001 | Permission / access-key cache lag (multi-instance) | **Mitigated** |
| H-002 | ListObjects cache not cleared on ACL changes | **Mitigated** |
| H-003 | No global max upload size | **Mitigated** |
| H-004 | No quotas / retention / legal hold | **Open** |
| H-005 | Bucket secrets returned on admin read | **Mitigated** |
| H-006 | Placement on unprobed buckets | **Mitigated** |
| H-007 | Multipart local disk assembly | **Partial** |
| H-008 | Search / facets in-memory | **Partial** |
| H-009 | Full folder-table walks | **Partial** |
| H-010 | No Prometheus `/metrics` | **Mitigated** |
| H-011 | No worker heartbeats | **Mitigated** (maintenance only) |
| H-012 | Processor DLQ / poison events | **N/A** (processors removed) |
| H-013 | No import from existing buckets | **Open** |
| H-014 | No file versioning | **Open** |
| H-015 | Narrow S3 client compatibility | **Open** |
| H-016 | Dev config does not fail readiness | **Open** |

### Operational notes (current implementation)

- **Shared caches** use `infra/cache/tiered.py` (process memory + Redis, generation
  bump on invalidate). Namespaces: `list_objects`, `access_key_active`,
  `folder_tree`, `folder_paths`, `effective_permissions`.
- **Redis availability:** if Redis is unavailable, invalidation may not propagate
  across API pods (local generation bump only). Treat Redis as a hard dependency
  for multi-replica cache coherence.
- **Invalidation:** folder grant/revoke, access-key mutations, and file/folder
  mutations call `uow.cache.invalidate_list_objects()` where listings can change.
- **Upload cap:** `MAX_OBJECT_BYTES` (default 5 GiB) enforced on PUT spool,
  blob create, and multipart complete (including streaming hash/assemble paths).
- **Placement:** `PLACEMENT_REQUIRE_REACHABLE_BUCKET=true` by default skips
  buckets without a recent successful probe for new writes.
- **Metrics:** `GET /metrics` (Prometheus); API + gateway + maintenance metrics.
- **Worker liveness:** maintenance worker writes Redis heartbeats;
  `/readyz` checks `workers.maintenance` when
  `MAINTENANCE_HEARTBEAT_REQUIRED=true` (default **false** — enable in prod).
- **Processors / file_events:** removed (migration 0024). H-012 applies only if
  durable outbound event consumers are reintroduced.

---

## Findings

### H-001: Permission and access-key revocation can lag behind admin changes

- **Area:** Access control, S3 gateway
- **Status:** **Mitigated.** Hot-path caches use `TieredCache` backed by Redis with
  generation-based invalidation. Access-key credentials, effective folder
  permissions, and folder tree/path snapshots are cached in shared namespaces.
  Grant/revoke and access-key create/revoke/delete invalidate the relevant
  namespaces (see `application/control_plane/grant_folder_access.py`,
  `access_key_mutations.py`, `infra/cache/folder_access.py`).
- **Residual risk:** Low if Redis is healthy. If Redis is down, invalidation may
  be process-local only until Redis recovers. `mark_access_key_used` debounce
  remains in-process (last-used timestamps only, not auth).
- **Impact:** High (was). Revoked grants or keys could remain effective in other
  pods until TTL expiry.
- **Suggested fix or mitigation:** Keep Redis highly available in multi-replica
  deployments. Optional: fail readiness when Redis cache invalidation is
  unavailable. Document revocation as eventually consistent only under Redis
  outage.

### H-002: S3 ListObjects cache is not cleared on permission changes

- **Area:** Access control, S3 gateway listings
- **Status:** **Mitigated.** `ListObjectsV2` responses are cached in the
  `list_objects` tiered namespace. `invalidate_list_objects()` bumps the
  generation on folder ACL grant/revoke, access-key mutations, and metadata
  mutations that affect listings. Cache keys include deployment scope and
  permission-relevant inputs (see `api/s3/helpers.py`).
- **Residual risk:** Same Redis outage caveat as H-001; default TTL
  `S3_LIST_OBJECTS_CACHE_TTL_SECONDS` (15s) bounds staleness.
- **Impact:** High (was). Revoked users could receive cached listings.
- **Suggested fix or mitigation:** None required for pilot if Redis is reliable.
  Add cross-pod integration tests if regressions are a concern.

### H-003: Uploads have no hard product limit

- **Area:** Uploads, S3 gateway, storage guardrails
- **Status:** **Mitigated.** `MAX_OBJECT_BYTES` in `settings.py` (default 5 GiB)
  enforced via `enforce_max_object_bytes()` in `ports/storage_policy.py` on:
  request body spool (`api/s3/helpers.py`), PUT path, blob create, multipart
  complete (hash and assemble loops). Per-backend `StorageCapabilities` limits
  still apply in addition.
- **Impact:** High (was). Unbounded uploads could exhaust disk or storage.
- **Suggested fix or mitigation:** Tune `MAX_OBJECT_BYTES` per environment;
  enforce matching limits at ingress if desired.

### H-004: Quotas and retention/deletion protection are not implemented

- **Area:** Data safety guardrails
- **Status:** **Open.**
- **Impact:** High. Users can consume unbounded storage; no legal hold or
  deletion protection on folders/files.
- **Suggested fix or mitigation:** Implement per-user, per-folder, and global
  quotas first, then add retention/deletion-protection checks to file, folder,
  S3 delete, and purge paths.

### H-005: Bucket credentials are returned in admin read responses

- **Area:** Bucket administration
- **Status:** **Mitigated.** Admin read/list responses use masked `key_id` and
  `secret_access_key` via `infra/db/stores/bucket_reads.py` and
  `utils/secrets.py`. Create/update still accept plaintext secrets; storage
  remains encrypted at rest. Tests: `test_bucket_read_responses_mask_credentials`.
- **Impact:** High (was). Decrypted secrets in API responses increased blast
  radius from logs and compromised admin sessions.
- **Suggested fix or mitigation:** Add explicit credential rotate endpoint if
  operators need to replace keys without recreating buckets.

### H-006: Placement can choose an unprobed or unreachable bucket

- **Area:** Object placement, bucket health
- **Status:** **Mitigated.** `choose_bucket()` excludes buckets with
  `reachable=False` when `PLACEMENT_REQUIRE_REACHABLE_BUCKET` is true (default).
  Admin/bootstrap can set the flag false. Tests in `test_s3_put.py`.
- **Impact:** Medium (was). New writes could target buckets with no successful
  probe history.
- **Suggested fix or mitigation:** Ensure maintenance probe cron runs before
  traffic; document bootstrap override.

### H-007: Multipart completion assembles the whole object through local disk

- **Area:** Multipart uploads, S3 gateway
- **Status:** **Partially mitigated.** When the storage adapter reports
  `server_side_copy`, completion uses `create_composed_blob` / storage compose
  (`UploadPartCopy` on S3, stream-into-final on filesystem) instead of a full
  local reassembly file. Pithosys still reads each part once to compute the
  canonical SHA-256 digest and sniff prefix. Fallback path (no server-side copy)
  still assembles via `SpooledTemporaryFile` with `MAX_OBJECT_BYTES` enforced
  per chunk.
- **Impact:** Medium. Very large multipart uploads on fallback backends can still
  stress API disk and CPU.
- **Suggested fix or mitigation:** Prefer S3-capable buckets for large multipart;
  dedicated assembly worker if filesystem backends must handle huge completes.

### H-008: Search and facets load all visible candidate files into memory

- **Area:** Search and metadata
- **Status:** **Partially mitigated.** `search_files()` uses
  `SearchStore.search_page()`: SQL `COUNT` + `ORDER BY` + `LIMIT/OFFSET` for
  the common path. Postgres pushes tags, keywords, and text `q` into JSONB/SQL.
  Portable/SQLite and queries with **KVS filters** still load candidates then
  filter in Python. **Facets** (`compute_facets`) still call `match_files` up to
  five times over the full visible set.
- **Impact:** Medium. Large libraries or heavy facet use can be slow or
  memory-heavy.
- **Suggested fix or mitigation:** SQL facet aggregation; KVS expression indexes;
  query timeouts; cap recursive search scope.

### H-009: Recursive folder walks scan the full folder table

- **Area:** Filesystem, permissions, search scopes
- **Status:** **Partially mitigated.** `cached_folder_tree_rows()` loads the
  folder table once per cache generation into tiered Redis; descendant IDs and
  paths are derived in memory from that snapshot. Invalidation on folder
  mutations clears tree/path/permission caches. Still O(all folders) per cache
  miss, not O(subtree) via closure table or recursive CTE.
- **Impact:** Medium. Very large folder trees increase cache refresh cost and
  memory per snapshot.
- **Suggested fix or mitigation:** Closure table, materialized path, or recursive
  CTE for descendant queries; optional per-subtree cache keys.

### H-010: Prometheus metrics endpoint is missing

- **Area:** Observability
- **Status:** **Mitigated.** `GET /metrics` exposes low-cardinality Prometheus
  metrics: API requests/duration, S3 gateway requests/duration, maintenance jobs,
  queue depth, bucket probe outcomes (`infra/metrics.py`, middleware in
  `api/app.py`).
- **Impact:** Medium (was). No scrape-based alerting.
- **Suggested fix or mitigation:** Wire dashboards/alerts in infra; optional
  OpenTelemetry traces later.

### H-011: Worker heartbeat state is missing

- **Area:** Maintenance operations
- **Status:** **Mitigated** for the shipped maintenance worker. Cron and job
  handlers call `touch_maintenance_heartbeat()`; `/readyz` includes
  `checks.workers.maintenance` via `maintenance_heartbeat_status()`. Strict
  failure when heartbeat is missing/stale requires
  `MAINTENANCE_HEARTBEAT_REQUIRED=true` (default false for local dev).
- **Impact:** Medium (was). Readiness could not prove workers were alive.
- **Suggested fix or mitigation:** Set `MAINTENANCE_HEARTBEAT_REQUIRED=true` in
  production; alert on stale heartbeat age. Add heartbeats for any future worker
  types (event dispatch, sniff, import).

### H-012: Processor failure handling depends on manual skip/rewind only

- **Area:** Event log and processors
- **Status:** **N/A.** The `processors` and `file_events` tables were removed.
  Unified `audit_events` + maintenance worker remain. Revisit when adding
  durable outbound file-event consumers (cursors, replay, DLQ).
- **Impact:** Medium (historical). Poison processor events could stall cursors.
- **Suggested fix or mitigation:** For new event sinks: outbox table, per-consumer
  cursor, lag metrics, bounded DLQ / quarantine.

### H-013: Import/sync from existing buckets is not available

- **Area:** Import and migration
- **Status:** **Open.**
- **Impact:** Medium. Preexisting object-store data cannot be adopted without
  custom tooling.
- **Suggested fix or mitigation:** Resumable import jobs (preserve keys as paths,
  progress reporting, audit events).

### H-014: File versioning is not available

- **Area:** Data safety
- **Status:** **Open.**
- **Impact:** Medium. Overwrites replace the logical file; no restore of prior
  versions.
- **Suggested fix or mitigation:** Version rows, restore API, retention for old
  versions, search filter for latest vs all versions.

### H-015: Native S3 compatibility coverage is still narrow

- **Area:** S3 gateway compatibility
- **Status:** **Open.** Core flows covered by tests (`test_s3_put`,
  `test_s3_listing_api`, `test_file_gateway_ops`). No virtual-hosted-style
  routing; limited compatibility harness vs AWS CLI / rclone / DuckLake workloads.
- **Impact:** Medium. Broader clients may hit unsupported behavior.
- **Suggested fix or mitigation:** Expand compatibility tests; publish supported
  S3 subset and stable error codes for unsupported operations.

### H-016: Configuration warnings do not fail readiness

- **Area:** Deployment safety
- **Status:** **Open.** `/readyz` reports dev defaults for secrets as
  `configuration.warnings` but overall status stays OK.
- **Impact:** Low. Misconfigured deployments can pass readiness.
- **Suggested fix or mitigation:** `PRODUCTION=true` (or similar) fails readiness
  on default `ENCRYPTION_SECRET`, `SESSION_SECRET`, `REDIS_PASSWORD`, admin
  password, or signing keys.
