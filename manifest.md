# Relic

> Every byte in its place.

## Vision

Relic is a metadata and discovery platform for object storage.

Relic is not an object store.

Relic is not a MinIO competitor.

Relic is not another S3-compatible storage backend.

Relic sits alongside existing object storage systems and continuously builds understanding of the data they contain.

The core idea is simple:

> S3 stores bytes. Relic understands them.

Users connect one or more existing buckets to Relic. Relic indexes them, tracks changes, enriches metadata, enables discovery, and allows users to organize objects without moving data.

---

# What Relic Is

Relic is:

* An object catalog.
* A metadata platform.
* A discovery engine.
* A search engine for object storage.
* A relationship graph for objects.
* A system for organizing objects without changing their physical location.
* A platform for attaching arbitrary metadata to objects.

Relic enables:

* Duplicate detection.
* Cross-bucket search.
* Object classification.
* Metadata enrichment.
* Virtual collections.
* Storage analytics.
* Cost analysis.
* Compliance analysis.
* Data discovery.

---

# What Relic Is Not

Relic is not:

* An object storage system.
* A filesystem.
* A replacement for S3.
* A replacement for MinIO.
* A replacement for Ceph.
* A backup system.
* A data lake.

Relic should avoid becoming responsible for storing customer bytes whenever possible.

Bytes already have a home.

Relic focuses on understanding them.

---

# Original Ingestion Idea

An earlier concept considered Relic as an ingestion service:

```text
Writers
   ↓
Relic
   ↓
S3
```

Potential features:

* Write smoothing.
* Small object batching.
* Segment storage.
* Compression.
* Deduplication.

Benefits:

* Reduced object counts.
* Better compression.
* Reduced metadata overhead.

Problems:

* Relic becomes part of the write path.
* Relic becomes responsible for durability.
* Relic becomes a storage system.
* Relic becomes difficult to adopt.

Conclusion:

This direction is technically interesting but significantly increases complexity and adoption friction.

Current recommendation:

Do not build ingestion first.

Focus on metadata and discovery first.

---

# Metadata-First Architecture

```text
             Bucket
                │
                ▼
          Initial Sync
                │
                ▼
            Relic DB
                ▲
                │
         Object Events
                │
                ▼
         Continuous Sync
```

Relic does not own storage.

Relic indexes storage.

---

# Synchronization Model

## Option 1: Periodic Scans

```text
Bucket
  ↓
Scan
  ↓
Relic
```

Advantages:

* Universal.
* No bucket configuration.

Problems:

* High load.
* Poor scalability.
* High latency.

For large buckets:

```text
10M+
100M+
objects
```

continuous full scans become impractical.

---

## Option 2: Event Notifications

```text
Bucket
   ↓
Notification
   ↓
Relic
```

Advantages:

* Near real-time.
* Low steady-state load.

Problems:

* Missed events.
* Event delivery failures.
* Relic downtime.

---

## Option 3: Hybrid (Preferred)

```text
Initial Sync
       +
Event Stream
       +
Background Verification
```

Workflow:

1. Perform initial bucket sync.
2. Subscribe to bucket notifications.
3. Process changes in real time.
4. Continuously verify correctness.

This provides:

* Near real-time updates.
* Eventual correctness.
* Scalable operation.

---

# Durable Event Transport

Direct delivery:

```text
Bucket
   ↓
Relic
```

is fragile.

Preferred:

```text
Bucket
   ↓
NATS JetStream
   ↓
Relic provider_events inbox
   ↓
batched job_runs
```

Benefits:

* No event loss during downtime.
* Replay capability.
* Better operational reliability.
* Relic-owned audit trail after an event is accepted.

---

# Bucket Reconciliation

Reconciliation exists for correctness.

Not freshness.

Relic should not repeatedly scan entire buckets.

Instead:

* Incremental verification.
* Sharded verification.
* Audit sampling.
* Drift detection.

Goal:

Detect divergence between Relic and storage.

---

# Technology Stack

## Go

Responsible for:

* Scanner.
* Event processing.
* Metadata engine.
* Search.
* API.
* Background jobs.
* Synchronization.

Why:

* Excellent concurrency.
* Single binary deployment.
* Efficient memory usage.
* Mature S3 ecosystem.

---

## TypeScript

Responsible for:

* Web UI.
* Dashboards.
* Search experience.
* Collection management.
* Administrative interfaces.

Likely stack:

* React
* Vite
* TanStack Query
* Tailwind

---

## Python

Optional.

Used for:

* OCR.
* Classification.
* NLP.
* Embeddings.
* AI enrichment.
* Content extraction.

Python should operate as workers.

Never as Relic's core.

---

# Metadata Philosophy

Relic should make very few assumptions about metadata.

Users define their own meaning.

Relic provides structure.

---

# Primitive Composition Principle

Relic features should be built as use cases of Relic's own primitives.

Avoid creating one-off subsystems when the same behavior can be expressed through:

* Objects.
* Attributes.
* Relations.
* Collections.
* Events.
* Jobs.

This keeps the product coherent.

Example:

Duplicate detection should not be a special side system.

It should be implemented as a core job that uses normal Relic primitives:

1. Read provider attributes such as `provider.etag`, `provider.size`, and object identity.
2. Search for objects with matching candidate signals.
3. Write job-owned attributes for candidate state when useful:

```yaml
job.detect_duplicates.potential_duplicates:
  - object_id_1
  - object_id_2
  - object_id_3
```

After verification, the job should create relations. The relation is the canonical duplicate result:

```text
duplicate
```

The feature is still "duplicate detection" from the user's perspective, but internally it is just Relic primitives composed together.

---

# Core Metadata Categories

## Core Metadata

Produced by Relic.

Example:

```yaml
core.object_id
core.bucket_id
core.first_seen_at
core.last_seen_at
```

Relic bookkeeping.

Catalog invariants.

Not provider claims.

---

## Provider Metadata

Observed from the connected storage provider.

S3-compatible object storage supports native metadata in more than one place:

* Object/system headers.
* User metadata headers.
* Object tags.

Capturing this should be part of Relic's core offering.

However, provider-native metadata should preserve its provider provenance instead of being blended into `core.*`.

Example:

```yaml
provider.etag
provider.size
provider.last_modified
provider.header.content_type
provider.header.cache_control
provider.header.content_disposition
provider.metadata.project
provider.metadata.owner
provider.metadata.source
provider.tag.environment
provider.tag.retention
```

Provider metadata is evidence, not truth.

Relic should not blindly promote provider-reported values into `core.*`.

For example, S3 `Content-Type` is often supplied by upload clients and can be wrong. It should be stored as:

```yaml
provider.header.content_type
```

If Relic later determines a MIME type by inspecting bytes, that result should be written by the component that performed the work, such as:

```yaml
job.extract_attributes.mime_type
job.extract_attributes.confidence
```

The distinction:

* `core.*` is Relic-owned bookkeeping and catalog invariants.
* `provider.*` is what the storage provider reported.
* `job.<job_type>.*` is derived, detected, or enriched metadata produced by Relic jobs.

---

## Derived Metadata

Produced by Relic jobs.

Example:

```yaml
job.extract_attributes.document_type
job.extract_attributes.language
job.extract_attributes.contains_faces
```

Opinionated.

Potentially incorrect.

Versionable.

Recomputable.

---

## Human Metadata

Produced by users.

Example:

```yaml
user.owner
user.project
user.comment
```

Business context.

Not derivable from bytes.

---

# Namespaces

Every attribute belongs to a namespace.

Namespace shape:

```text
core.*
provider.<attribute_name>
provider.header.<header_name>
provider.metadata.<metadata_key>
provider.tag.<tag_key>
provider.<provider_name>.<provider_specific_attribute>
job.<job_type>.<attribute_name>
job.<job_type>.<attribute_name>.*
user.<attribute_name>
user.<attribute_name>.*
```

Rules:

* `core.*` is reserved for Relic bookkeeping and catalog invariants.
* `provider.*` is for metadata observed from a storage provider.
* Common provider-reported fields should be flattened, such as `provider.etag` and `provider.size`.
* Provider-specific fields may include the provider name deeper in the namespace, such as `provider.s3.storage_class`.
* `job.<job_type>.*` is for metadata produced by built-in Relic jobs such as `extract_attributes` and `detect_duplicates`.
* `user.*` is for user-owned metadata.
* Plugin and workflow namespaces are deferred until those systems become first-class product scope.

Examples:

```text
core.object_id
core.first_seen_at
provider.etag
provider.size
provider.header.cache_control
provider.metadata.project
provider.metadata.source
provider.tag.environment
job.extract_attributes.mime_type
job.detect_duplicates.potential_duplicates
user.owner
user.review.status
```

Benefits:

* No collisions.
* Clear ownership.
* Better governance.

---

# Core Domain Model

## Bucket

```yaml
Bucket:
  id
  name

  endpoint
  region

  provider

  encrypted_credentials

  created_at
  updated_at

  last_sync_at
  last_event_at
```

Bucket sync settings are deferred for the MVP. Bucket creation and the manual sync button should enqueue hardcoded `sync_bucket` job runs instead of storing per-bucket schedules.

Credentials should be stored encrypted in Relic's database.

Reason:

* Users should be able to connect buckets from the UI.
* Relic should be easy to run locally or self-host without external secret infrastructure.
* Bucket onboarding should not require Kubernetes, Vault, Infisical, or manual operator setup.

Requirements:

* Never store plaintext credentials.
* Encrypt credentials before persistence.
* Keep encryption keys outside the database.
* Support key rotation.
* Avoid returning credential secrets from read APIs.
* Redact credentials in logs, events, jobs, and audit records.

External secret managers may be supported later for larger deployments, but encrypted database storage should be the default onboarding path.

---

## Object

Represents a bucket entry.

```yaml
Object:
  id

  bucket_id
  key

  attributes
  attribute_provenance

  created_at
  updated_at
```

Object rows mirror Relic's current catalog view of bucket contents.

Relic should not add a soft-delete flag for objects in the MVP. If an object no longer exists in the bucket, the sync or remove job should remove the catalog row. Historical visibility belongs in job runs, events, and audit records, not on the active object row.

`created_at` and `updated_at` are database bookkeeping for the catalog row. They are not object metadata.

Object lifecycle facts that users may query, such as when Relic first or last observed the object, should live in `Object.attributes`:

Object attributes should be stored as a JSONB document.

Example:

```json
{
  "core": {
    "object_id": "object_123",
    "first_seen_at": "2026-06-23T00:00:00Z",
    "last_seen_at": "2026-06-26T00:00:00Z"
  },
  "provider": {
    "etag": "\"abc123\"",
    "size": 1048576,
    "last_modified": "2026-06-22T12:00:00Z",
    "metadata": {
      "source": "wikipedia.org"
    }
  },
  "job": {
    "detect_duplicates": {
      "potential_duplicates": ["object_456"]
    }
  },
  "user": {
    "owner": "finance"
  }
}
```

Object attribute provenance should also be stored as a compact JSONB document.

Every automated mutation that writes attributes should produce a job run. Attribute provenance then maps attribute paths or path prefixes to the run that produced them. User edits can point to direct user-edit provenance.

Example:

```json
{
  "provider": "run.sync_123",
  "job.detect_duplicates": "run.detect_duplicates_456",
  "user.owner": "user.update_223"
}
```

Resolution rule:

1. Look for an exact path, such as `user.owner`.
2. If none exists, walk up prefixes, such as `job.detect_duplicates`, then `job`.
3. If none exists, fall back to object-level sync or creation provenance if available.

This keeps provenance row counts bound to object counts while still making attribute provenance explainable.

---

## Attribute

Relic should not create an `attributes` table for the MVP.

The hot query surface is `Object.attributes`, a JSONB document on the object row. Attribute provenance is `Object.attribute_provenance`, another JSONB document on the object row.

This avoids duplicating the same attribute model in both JSONB and rows. If JSONB stops being enough, Relic can add projections, generated columns, or a search index without changing the logical model.

The namespace is not enough provenance by itself. It says who owns the meaning of an attribute. It does not say which user, job type, run, or implementation version produced the current value. The referenced run or user edit carries that context.

---

# Attribute Types

Attribute values are JSON values, but definitions should describe the expected logical type for validation and UI rendering.

Supported logical types should include:

```text
String
Integer
Float
Boolean
Timestamp
JSON
StringArray
```

Avoid storing everything as strings.

Typed querying is critical.

---

# Attribute Definitions

Optional registry:

```yaml
AttributeDefinition:
  namespace
  key

  value_type

  description
```

Allows:

* Documentation.
* Validation.
* Better UI.

---

# Relations

Objects may relate to one another.

Relic should not define a fixed set of relation types.

The relation type is defined by whoever creates the relation:

* A user.
* A Relic job.
* A future workflow or extension.

Relic stores the relation and provides querying, visualization, and governance around it. Relic does not decide what relation types are valid unless an optional registry or validation rule is configured.

```yaml
Relation:
  id

  source_object
  target_object

  relation_type

  attributes

  created_by_type
  created_by_id
  created_by_name
  created_by_run_id

  created_at
  updated_at
```

Duplicate detection should create `duplicate` relations after verification. Relic does not need a separate `Content` table for this in the MVP. If the duplicate job computes a hash or records match evidence, that evidence can live on the relation's `attributes` document or under object-level job attributes.

Example relation types:

```text
duplicate
thumbnail_of
derived_from
references
contains
```

---

# Collections

Collections are saved searches.

Not folders.

Not physical groups.

Collections may be created by:

* Users.
* Relic jobs.
* Future workflows or extensions.

Relic should not assume that collections are only manually curated UI objects. A core job might create a collection for suspected duplicates, or a future workflow might create a collection for objects that need review.

Example:

```sql
job.extract_attributes.mime_type = 'application/pdf'
AND user.owner = 'finance'
```

Stored as:

```yaml
Collection:
  id

  name
  description

  query

  owner

  created_by_type
  created_by_id
  created_by_name
  created_by_run_id

  created_at
  updated_at
```

Collections update automatically because membership is derived from the stored query, not from manually maintained object lists.

Default behavior:

* Store the collection query.
* Evaluate the query when collection objects are requested.
* Newly matching objects appear without any explicit "add to collection" operation.
* Objects that stop matching disappear without any explicit "remove from collection" operation.

For expensive or frequently used collections, Relic may maintain a materialized membership cache:

* Object, attribute, relation, and job events mark affected collections dirty.
* Background jobs recompute dirty collections.
* Reads can use cached membership when fresh enough.
* The query remains the source of truth.

This keeps collections declarative while still allowing performance optimizations later.

---

# Query Language

Initial recommendation:

Do not invent one.

Use:

* SQL
* SQL-like DSL
* Structured query builder

Inventing a new language creates unnecessary complexity.

Potential future direction:

Translate a custom UI query model into SQL.

---

# Event Log

Useful for observability.

```yaml
Event:
  id

  object_id

  event_type

  payload

  timestamp
```

Examples:

```text
object_discovered
object_removed
attribute_added
attribute_changed
scan_completed
```

---

# Job System

```yaml
JobRun:
  id

  type

  state

  progress

  input

  result

  created_at
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

---

# Future Extensions

Plugin-like extensions are deferred.

The MVP should use built-in Relic jobs for sync, object import/remove/refresh, attribute extraction, duplicate detection, and cleanup. Extension APIs should not be part of the core model until Relic has a clear need for third-party or user-defined execution.

Future extensions may produce metadata.

Not owners of data.

Example:

```text
Object
   ↓
Extension
   ↓
Attributes
```

Relic stores the result.

Extensions should not modify storage directly.

Extensions may later define actions and triggers for workflows.

---

# Workflows

Workflows, flows, or automations are deferred user-defined chains of triggers and actions.

They should be first-class Relic primitives rather than bespoke feature code.

Workflow:

```yaml
Workflow:
  id

  name
  description

  enabled

  trigger
  actions

  owner

  created_at
  updated_at
```

Triggers describe when a workflow runs.

Examples:

```text
cron
interval
object_discovered
attribute_added
attribute_changed
extension_completed
job_completed
user_action
webhook_received
```

Actions describe what the workflow does.

Examples:

```text
run_extension
add_attribute
delete_objects
dedupe_objects
move_object
call_webhook
create_collection
start_job
```

Workflows should operate through Relic's own APIs and primitives.

For example:

* The `detect_duplicates` job can flag potential duplicates.
* A user can define a workflow that triggers when verified duplicates are found.
* The workflow can notify a webhook, create a review collection, or run a dedupe action.

Actions that modify object storage should be explicit, permissioned, auditable, and reversible where possible.

---

# Auth Model

Relic should support both human and machine access.

Human access:

* Humans authenticate through OIDC.
* Humans use the web UI.
* Humans can create API tokens for machines.

Machine access:

* Machines authenticate with API keys or API tokens.
* API tokens should be created by authenticated humans.
* API tokens should be stored hashed, not plaintext.
* API tokens should be accepted as bearer tokens.

Likely flow:

1. Human logs into Relic through OIDC.
2. Human creates an API token.
3. Human gives the token to a machine, script, service, or integration.
4. Machine accesses Relic APIs using that token.

Every API endpoint should be designed as authenticated by default, except explicitly public operational endpoints such as health checks.

Auth should be configurable:

```text
AUTH_ENABLED=false
```

For early development, auth may be disabled by default. If `AUTH_ENABLED=true` before auth is implemented, Relic should fail clearly with a "not implemented" error rather than silently running with partial auth.

---

# Likely API Endpoints

## Buckets

```http
GET    /api/buckets
POST   /api/buckets

GET    /api/buckets/:id
PATCH  /api/buckets/:id
DELETE /api/buckets/:id

POST   /api/buckets/:id/sync
```

---

## Objects

```http
GET /objects

GET /objects/:id

GET /objects/search

GET /objects/:id/attributes

GET /objects/:id/relations
```

---

## Attributes

```http
GET    /attributes

POST   /attributes

PATCH  /attributes/:id

DELETE /attributes/:id
```

---

## Collections

```http
GET    /collections

POST   /collections

GET    /collections/:id

PATCH  /collections/:id

DELETE /collections/:id

GET    /collections/:id/objects
```

---

## Relations

```http
GET    /relations

POST   /relations

DELETE /relations/:id
```

---

## Job Runs

```http
GET /api/job-runs

GET /api/job-runs/:id
```

---

## Search

```http
POST /search
```

Potentially:

```json
{
  "filters": [...]
}
```

---

## Events

```http
GET /events
```

---

## Future Extensions

```http
Extension APIs are deferred.
```

---

## Workflows

```http
Workflow APIs are deferred.
```

---

# Future Possibilities

Potential future features:

* Semantic search.
* OCR.
* Embeddings.
* Document understanding.
* Compliance reporting.
* Sensitive data detection.
* Cost optimization recommendations.
* Duplicate cleanup automation.
* Cross-provider inventory.
* Data governance tooling.

---

# Business Positioning

Do not sell metadata.

Sell outcomes.

Examples:

* Discover what you have.
* Find duplicates.
* Understand storage usage.
* Organize data without moving it.
* Search across buckets.
* Reduce storage costs.
* Improve governance.

Relic should be positioned as:

> The understanding layer for object storage.

Not:

> Another place to store objects.

---

# Final Principle

Relic should remain focused on one responsibility:

> Build and maintain a continuously accurate understanding of the objects that already exist.

The moment Relic starts trying to become an object store, filesystem, ingestion platform, backup product, data lake, AI platform, and governance suite simultaneously, it loses its identity.

The strongest version of Relic is simple:

Connect buckets.

Build understanding.

Stay correct.

Everything else builds on top of that.
