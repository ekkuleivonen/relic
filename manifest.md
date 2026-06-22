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
         Initial Import
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
Initial Import
       +
Event Stream
       +
Background Verification
```

Workflow:

1. Perform initial bucket import.
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
Kafka
SQS
RabbitMQ
   ↓
Relic
```

Benefits:

* No event loss during downtime.
* Replay capability.
* Better operational reliability.

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

# Core Metadata Categories

## Core Metadata

Produced by Relic.

Example:

```yaml
core.mime_type
core.size
core.sha256
core.etag
```

Objective.

Reconstructable.

Machine-verifiable.

---

## Derived Metadata

Produced by plugins.

Example:

```yaml
ai.document_type
ai.language
ai.contains_faces
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

Examples:

```text
core.*
user.*
ai.*
github.*
jira.*
plugin.*
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

  last_scan_at
  last_event_at

  sync_status
```

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

## Content

Represents physical content.

```yaml
Content:
  id

  sha256

  size

  created_at
```

Used for deduplication.

---

## Object

Represents a bucket entry.

```yaml
Object:
  id

  bucket_id
  key

  content_id

  size
  etag

  mime_type

  created_at
  modified_at

  first_seen_at
  last_seen_at

  deleted
```

Objects reference content.

Multiple objects may reference identical content.

---

## Attribute

```yaml
Attribute:
  id

  object_id

  source_type
  source_name

  namespace

  key

  value

  value_type

  confidence

  created_at
  updated_at
```

---

# Attribute Types

Supported types should include:

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

```yaml
Relation:
  id

  source_object
  target_object

  relation_type
```

Examples:

```text
duplicate_of
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

Example:

```sql
core.mime_type = 'application/pdf'
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

  created_at
```

Collections update automatically.

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
object_deleted
attribute_added
attribute_changed
scan_completed
```

---

# Job System

```yaml
Job:
  id

  type

  state

  progress

  payload

  created_at
```

Examples:

```text
scan_bucket
reconcile_bucket
plugin_execution
index_rebuild
```

---

# Plugins

Plugins should be producers of metadata.

Not owners of data.

Example:

```text
Object
   ↓
Plugin
   ↓
Attributes
```

Relic stores the result.

Plugins do not modify storage.

---

# Likely API Endpoints

## Buckets

```http
GET    /buckets
POST   /buckets

GET    /buckets/:id
PATCH  /buckets/:id
DELETE /buckets/:id

POST   /buckets/:id/import
POST   /buckets/:id/reconcile
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

## Jobs

```http
GET /jobs

GET /jobs/:id
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

## Plugins

```http
GET /plugins

POST /plugins/:id/run
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
* Duplicate cleanup workflows.
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
