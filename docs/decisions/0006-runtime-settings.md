# 0006: Runtime settings

Date: 2026-06-28

## Status

Accepted

## Context

Most operational configuration in Pithosys was loaded from environment variables at process startup. That made it awkward to tune worker polling, job schedulers, and similar knobs without redeploying or editing `.env` on every host.

We needed a runtime configuration store for worker and job settings while keeping bootstrap concerns (database connectivity, encryption keys, auth) in environment variables.

## Decision

### Bootstrap (env only)

These stay in `.env` and are read once at process startup:

- `DATABASE_URL`, `HTTP_ADDR`, `LOG_LEVEL`
- All auth settings (`SUPERUSER_*`, `SESSION_*`, `WEB_APP_URL`, OIDC)
- `ENCRYPTION_KEY_*`

### Runtime (database)

A `settings` table stores flat key-value pairs using the same names as the former env vars:

```sql
CREATE TABLE settings (
    key        text PRIMARY KEY,
    value      text NOT NULL,
    encrypted  boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text
);
```

`SeedSettings()` inserts missing keys with defaults and never overwrites admin changes.

Canonical keys:

| Key | Default | Purpose |
|-----|---------|---------|
| `WORKER_RUNNER_POLL_INTERVAL` | `2s` | Job runner idle poll |
| `WORKER_RUNNER_RETRY_DELAY` | `30s` | Failed job retry backoff |
| `WORKER_SCAN_SCHEDULER_INTERVAL` | `2s` | Scan scheduler tick |
| `WORKER_SCAN_STAGGER` | `30s` | Delay between bucket scan enqueues |
| `WORKER_DUPLICATE_DETECTION_SCHEDULER_INTERVAL` | `2s` | Duplicate detection scheduler tick |
| `WORKER_UPSTREAM_PROCESSOR_INTERVAL` | `2s` | Upstream event processor tick |
| `WORKER_CONFIG_REFETCH_INTERVAL` | `5m` | Settings cache refresh |
| `SCAN_BUCKET_ENABLED` | `true` | Global scan scheduler enable |
| `SCAN_BUCKET_INTERVAL` | `24h` | Global scan cadence |
| `DUPLICATE_DETECTION_ENABLED` | `false` | Duplicate detection enable |
| `DUPLICATE_DETECTION_INTERVAL` | `24h` | Duplicate detection cadence |

Removed env vars: `WORKER_POLL_INTERVAL`, `WORKER_BATCH_LATENCY`, and all keys above.

### API

- `GET /api/settings` — any authenticated user
- `PATCH /api/settings/{key}` — admin only; unknown keys rejected

### Worker runtime model

The worker uses a supervisor pattern:

1. Refresh an in-memory settings cache from the database every `WORKER_CONFIG_REFETCH_INTERVAL`
2. Always-on loops (job runner, upstream processor, JetStream manager) read intervals from the cache and sleep with `time.After`
3. Supervised schedulers (scan, duplicate detection) are started/stopped based on enable flags

No process restart is required for interval or enable changes.

### Per-bucket scan settings

Per-bucket `pithosys_config.scan.enabled` and `pithosys_config.scan.interval` are ignored. Scan scheduling uses global `SCAN_BUCKET_ENABLED` and `SCAN_BUCKET_INTERVAL` only. Existing per-bucket values remain in the database but have no effect.

## Consequences

- Admins manage worker and job knobs from Settings → Worker / Jobs in the UI
- `.env` shrinks to bootstrap-only variables
- The `encrypted` column exists for future secret settings; v1 stores no secrets in the database
- Upstream capture fields remain a separate domain table and UI for now
