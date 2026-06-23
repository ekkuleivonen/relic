# Relic MVP

## Goal

Build the smallest credible version of Relic:

> Connect a bucket, import its object inventory, store useful metadata, and make it searchable.

The MVP should prove Relic's core loop before expanding into plugins, event streams, reconciliation, AI enrichment, or governance workflows.

## First Product Slice

The first usable Relic flow should be:

1. Add a bucket from the UI.
2. Store bucket credentials encrypted in the database.
3. Run an initial import.
4. Persist objects and core metadata.
5. Search or list imported objects.
6. Show sync/import job status.

This is the first "real Relic" loop. If this works well, the rest of the platform has a foundation.

## Initial Scope

Include:

* Bucket creation from the UI.
* Encrypted credential persistence.
* S3-compatible bucket access.
* Initial full bucket import.
* Object catalog persistence.
* Basic object list/search.
* Import job state and progress.
* Auth middleware shape, disabled by default until implemented.
* Health endpoint and basic operational visibility.

Exclude for now:

* Plugins.
* Relations.
* Collections.
* AI enrichment.
* OCR.
* Embeddings.
* Event streams.
* Reconciliation.
* Duplicate cleanup workflows.
* Cost optimization.
* Compliance reporting.

These are important later, but they only make sense after the initial catalog loop works.

## Backend Contracts To Define First

Define backend contracts before building much UI.

### Auth

Every API endpoint should be designed as authenticated by default, except explicitly public operational endpoints such as health checks.

Initial auth modes:

* Human auth through OIDC.
* Machine auth through API keys or API tokens.

Likely flow:

1. A human logs into the UI through OIDC.
2. The human creates API tokens in Relic.
3. Machines use those API tokens for API access.

Configuration:

```text
AUTH_ENABLED=false
```

For now, `AUTH_ENABLED` should default to `false`. If set to `true` before auth is implemented, Relic should fail clearly with a "not implemented" error rather than silently running with partial auth.

Go implementation direction:

* Use normal `net/http` middleware patterns for request authentication.
* Treat authenticated callers as principals.
* Represent principals as human users, API tokens, plugins, or workflows as the platform grows.
* Validate OIDC tokens with a well-maintained OIDC library.
* Store API tokens hashed, not plaintext.
* Accept machine tokens as bearer tokens.

API tokens should use one-way token handling, not reversible credential encryption. Relic should generate high-entropy tokens, store a lookup prefix for candidate row lookup, and store an Argon2id hash envelope for verification. Plaintext API tokens should only be shown once at creation time.

Auth should be enforced at the API boundary and carried through application services as caller context. Route handlers should not manually reimplement auth checks.

### Bucket API

Required operations:

```http
GET    /api/buckets
POST   /api/buckets
GET    /api/buckets/:id
PATCH  /api/buckets/:id
DELETE /api/buckets/:id
POST   /api/buckets/:id/import
```

Bucket creation should accept provider details, credentials, prefix or scope, non-secret provider config, and plugin settings. Read responses must never return plaintext credential secrets.

Bucket fields should be split by ownership:

* Top-level bucket fields are Relic's provider-neutral connection and scope model: provider, endpoint URL, region, bucket name, and prefix.
* `provider_config` is for non-secret adapter-specific options that Relic does not interpret generically, such as S3 path-style addressing, compatibility flags, TLS options, or provider-specific signing details.
* Credentials are secret material and must be encrypted separately from provider config.
* `plugin_settings` is for plugin-owned ongoing behavior.

Example S3-compatible provider config:

```json
{
  "s3": {
    "force_path_style": true,
    "signing_region": "us-east-1"
  }
}
```

For the MVP, manual import is the only special bucket lifecycle action:

```http
POST /api/buckets/:id/import
```

This creates an import job and updates catalog state as the job runs.

Ongoing behavior should be represented as plugin-owned settings, not as special bucket subsystems. The bucket contract should reserve a JSONB-friendly plugin settings shape:

```json
{
  "plugins": {
    "background_verification": {
      "enabled": true,
      "settings": {
        "interval": "24h",
        "sample_rate": 0.01
      }
    },
    "duplicate_detection": {
      "enabled": false,
      "settings": {}
    }
  }
}
```

Future scheduled imports, background verification, and reconciliation can become plugin settings once those concepts are sharper.

### Credential Encryption

Define:

* Credential input shape per provider.
* Encrypted credential storage format.
* Encryption key configuration.
* Key identifier storage for rotation.
* Redaction rules for logs, jobs, events, and API responses.

Requirements:

* Never persist plaintext credentials.
* Keep encryption keys outside the database.
* Make local/self-hosted setup straightforward.
* Support future key rotation.

MVP configuration:

```text
ENCRYPTION_KEY_ID=local-dev
ENCRYPTION_KEY_BASE64=<32-byte base64 key>
```

Generate a local key with:

```sh
openssl rand -base64 32
```

The API process should decode `ENCRYPTION_KEY_BASE64`, require exactly 32 bytes, construct a `secrets.Manager`, and inject that manager into services that need to encrypt or decrypt credentials. Storage must only persist `secrets.Envelope` values and must not read encryption configuration or perform encryption itself.

### Import Job Lifecycle

Define:

* Job states.
* Progress fields.
* Error representation.
* Retry behavior.
* Cancellation behavior, if any.

Initial states:

```text
pending
running
succeeded
failed
cancelled
```

### Object Schema

Persist at least:

* Bucket ID.
* Object key.
* Provider-reported size.
* Provider-reported ETag.
* Provider-reported last modified time.
* Provider-reported content type where available.
* S3-compatible provider headers where available.
* S3-compatible user metadata where available.
* S3-compatible object tags where available.
* First seen time.
* Last seen time.
* Deleted/tombstone flag.

For duplicate detection, `provider.etag + provider.size` is enough to identify potential duplicates during the first import pass. Relic should not hash every object body up front.

Duplicate verification should be two-phase:

1. Group imported objects by `provider.etag + provider.size`.
2. Flag matching groups as potential duplicates.
3. Compute SHA-256 only for potential duplicate groups.
4. Mark matching hashes as verified duplicates.

This keeps initial import cheap while still allowing Relic to confirm duplicates before presenting them as certain.

### Search/List API

Start with simple list and filter behavior:

* Bucket filter.
* Prefix filter.
* Provider-reported content type filter if available.
* Size range.
* Modified time range.
* Text match against object key.

Avoid inventing a custom query language for the MVP.

### Provider Adapter Interface

Define a minimal S3-compatible adapter interface:

* Validate credentials.
* List objects by bucket/prefix.
* Fetch object metadata.
* Fetch provider-native headers, user metadata, and tags where supported.
* Optionally open object stream for future hashing/enrichment.

Keep provider-specific details out of route handlers and core domain logic.

## Implementation Plan

### 1. Backend Skeleton

Create the Go backend foundation:

Status:

* Done: Config loading.
* Done: HTTP server.
* Done: Health endpoint.
* Done: Generated OpenAPI and docs through Huma.
* Done: `AUTH_ENABLED=false` by default, with `AUTH_ENABLED=true` failing clearly until implemented.
* Done: Structured startup/shutdown logging with Go `slog`.
* Done: Database connection.
* Done: Basic request/response error handling.

### 2. Database Access Layer

Create a DB access layer for Postgres persistence.

Status:

* Done: `packages/storage` wraps Postgres access behind a shared `Store`.
* Done: HTTP dependencies receive `*storage.Store` instead of raw `*pgxpool.Pool`.
* Done: Transaction helper shape exists through `Store.WithTx`.
* Done: Bucket repository contract exists.
* Done: Bucket create, get, and list are implemented behind the storage layer.
* Done: JSONB helper primitives exist for future centralized JSONB handling.
* Pending: Bucket update and delete persistence.
* Pending: Object, content, and job repositories.
* Pending: Broader integration tests for future repositories.

Rules:

* Application code must go through the DB abstraction.
* Do not skip around it for convenience.
* Keep database-specific SQL and capabilities isolated behind repositories or query builders.
* Use Postgres-specific optimizations where useful, but keep them contained.
* Keep JSONB query construction centralized.
* Make tests cover the abstraction instead of individual callers relying on database details.

This is not about supporting multiple databases in the MVP. It is about keeping persistence logic disciplined and preventing route handlers, services, workers, plugins, or workflows from going around the storage layer.

### 3. Database Schema

Create initial tables for:

* `buckets`
* `objects`
* `contents`, for verified duplicate content
* `jobs`

The `buckets` table should include bucket identity, provider-neutral connection and scope fields, encrypted credentials, `provider_config` JSONB, and `plugin_settings` JSONB. Scheduled import, background verification, and reconciliation settings should remain plugin-owned rather than hardcoded bucket columns.

Status:

* Done: `golang-migrate` migration runner is wired into API startup.
* Done: Initial `buckets` migration exists.
* Done: `buckets` includes provider-neutral connection and scope fields.
* Done: `buckets` stores encrypted credential envelope fields.
* Done: `buckets` includes `provider_config` JSONB for non-secret adapter-specific options.
* Done: `buckets` includes `plugin_settings` JSONB for plugin-owned behavior.
* Pending: `objects` table.
* Pending: `contents` table for verified duplicate content.
* Pending: `jobs` table.

The `objects` table should include:

* `attributes` JSONB for provider, user, plugin, workflow, and core attributes.
* `attribute_provenance` JSONB mapping attribute paths or prefixes to job IDs.

Every attribute mutation should be represented by a job or run record, including user edits. This keeps provenance compact while avoiding one provenance row per object attribute.

Do not overbuild the schema for plugins, relations, or collections yet.

### 4. Credential Encryption

Implement and test credential encryption before bucket CRUD:

Status:

* Done: `packages/secrets` defines a `Manager` interface and encrypted `Envelope`.
* Done: Static XChaCha20-Poly1305 key manager exists.
* Done: Encryption key ID and key material are loaded from config.
* Done: Bucket creation encrypts credential JSON before persistence.
* Done: Bucket responses omit plaintext credentials and encrypted credential envelopes.
* Done: Credential encryption behavior is covered by tests.
* Pending: Provider-facing decrypt path when scanner/import needs credentials.
* Pending: Full redaction checks for future logs, jobs, and events.

* Encrypt credentials before persistence.
* Decrypt only inside backend services that need provider access.
* Redact credentials from API responses and logs.
* Store a key identifier with encrypted payloads.

### 5. Bucket CRUD API

Implement:

Status:

* Done: `POST /api/buckets`.
* Done: `GET /api/buckets`.
* Done: `GET /api/buckets/:id`.
* Done: `PATCH /api/buckets/:id`.
* Done: Bucket API is registered in generated OpenAPI docs.
* Done: Bucket create encrypts credentials before calling storage.
* Done: Bucket read responses redact credentials.
* Pending: `DELETE /api/buckets/:id`.
* Pending: `POST /api/buckets/:id/import`.
* Pending: Optional credential validation against the provider before saving.

Operations:

* Create bucket.
* List buckets.
* Get bucket.
* Update bucket connection config and plugin settings.
* Delete bucket.

Bucket creation should optionally validate credentials against the provider before saving.
Bucket update should allow changing plugin settings without replacing credentials.

### 6. S3-Compatible Scanner

Implement initial object listing for S3-compatible buckets:

* Paginated listing.
* Prefix handling.
* Continuation tokens.
* Basic metadata capture.
* Retry behavior for transient provider errors.

### 7. Background Import Job

Implement bucket import as a background job:

* Create job record.
* Mark job running.
* Scan bucket.
* Upsert object records.
* Track progress.
* Mark succeeded or failed.

For the MVP, a simple in-process worker is acceptable. A durable external queue can come later if needed.

### 8. Vite Web UI

Build the smallest UI around the core loop:

* Add bucket form.
* Bucket list.
* Trigger import.
* Job status view.
* Object table.
* Basic filters/search.

Use React, Vite, TanStack Query, Tailwind, and shadcn UI components.

## Database Choice

Relic will use Postgres for the MVP.

Object attributes should be stored in JSONB and indexed with GIN. This is the primary query substrate for search, filtering, and collections until there is real evidence that a dedicated search engine is needed.

Rules:

* Do not support SQLite in the MVP.
* Never bypass the DB abstraction from route handlers, services, workers, plugins, or workflows.
* Keep JSONB query construction inside the persistence layer.
* Use generated columns or dedicated indexes for hot paths when needed.
* Keep attribute provenance in a compact JSONB sidecar, not inside the hot attribute document.
* Do not create one provenance row per object attribute for the MVP.
* Test important persistence behavior against Postgres before calling the MVP complete.

## Near-Term Non-Goals

Do not build these until the initial catalog loop is working:

* Durable event transport.
* Continuous sync.
* Reconciliation.
* Attribute plugins.
* Semantic search.
* Duplicate cleanup workflows.
* Object relationship graph.
* Governance dashboards.
* Workflow/automation engine.
* Multi-tenant authorization model.

## Success Criteria

The MVP is successful when a user can:

1. Start Relic locally.
2. Open the web UI.
3. Add an S3-compatible bucket.
4. See credentials accepted without manual secret-manager setup.
5. Trigger an import.
6. Watch import progress.
7. Browse and search imported objects.
8. Restart Relic without losing catalog state.

At that point, Relic has proven its core identity:

> Connect buckets. Build understanding. Stay correct.
