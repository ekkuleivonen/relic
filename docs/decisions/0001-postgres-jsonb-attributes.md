# ADR 0001: Use Postgres With JSONB Attributes

## Status

Accepted

## Context

Relic's core query pressure will come from attributes.

Attributes need to support typed values, nested data, arrays, upstream metadata, plugin output, workflow output, user metadata, filtering, sorting, and collection queries.

Trying to support SQLite and Postgres at the same time would add abstraction burden before the product has proven its core loop.

Postgres gives Relic a strong MVP substrate:

* JSONB for flexible attribute documents.
* GIN indexes for attribute filtering.
* B-tree indexes and generated columns for common hot paths.
* Transactions and locking semantics suitable for import jobs.
* A future path to heavier indexing or search engines if needed.

## Decision

Relic will use Postgres as the required database for the MVP.

Relic will store object attributes in JSONB and index them with GIN.

Relic will not support SQLite for the MVP.

Months from now, if JSONB queries become insufficient, Relic may layer a dedicated search engine on top. Until then, Postgres JSONB is the source of truth and primary query substrate.

Relic will still use a database access layer as the only supported path for application code to interact with persistence.

Route handlers, services, workers, plugins, and workflows must not bypass this abstraction.

The abstraction is no longer about database portability. It is about persistence discipline, testability, and keeping SQL out of unrelated product logic.

Postgres-specific optimizations are allowed and expected, but they must remain behind repositories, stores, query builders, or equivalent DB access components.

## Consequences

This gives Relic:

* One database target for the MVP.
* A flexible attribute model without designing a custom query engine.
* GIN-backed filtering over JSONB attributes.
* A clear path to generated columns or additional indexes for hot queries.
* A clear place to contain SQL and persistence behavior.
* Less risk from lowest-common-denominator database design.

This also costs Relic:

* Users must run Postgres.
* Local setup is heavier than SQLite.
* JSONB query patterns need discipline.
* Large-scale search may eventually require a dedicated search engine.
* Code review must prevent callers from bypassing the persistence layer.

## Attribute Storage

Objects should expose one JSONB attribute document as the hot query surface.

Example:

```json
{
  "core": {
    "object_id": "object_123",
    "first_seen_at": "2026-06-23T00:00:00Z"
  },
  "upstream": {
    "etag": "\"abc123\"",
    "size": 1048576,
    "last_modified": "2026-06-22T12:00:00Z",
    "metadata": {
      "source": "wikipedia.org"
    },
    "tag": {
      "environment": "prod"
    }
  },
  "plugin": {
    "duplicate_detection": {
      "potential_duplicates": ["object_456", "object_789"]
    }
  },
  "user": {
    "owner": "finance"
  }
}
```

This document should be queryable with JSONB operators and indexed with GIN.

Common hot fields may later get generated columns or dedicated indexes without changing the logical attribute model.

## Upstream Field Normalization

Common upstream-reported fields should be flattened under `upstream.*`.

Examples:

```text
upstream.etag
upstream.size
upstream.last_modified
upstream.header.content_type
upstream.metadata.source
upstream.tag.environment
```

A upstream field should be flattened when it has a common meaning across more than one or two upstreams.

Upstream-specific fields can be ignored initially. If needed later, they may be added under upstream-specific subnamespaces.

Example:

```text
upstream.s3.storage_class
upstream.gcs.generation
```

Upstream metadata is evidence, not truth. Upstream-reported values must not be promoted into `core.*`.

## Provenance Storage

Namespaces are not enough for provenance.

The namespace tells Relic who owns the meaning of an attribute, but not which actor, version, job, or run produced a specific value.

Relic should keep provenance separate from the hot JSONB attribute document, but it should still be stored per object rather than per attribute row.

Objects should have a compact JSONB provenance sidecar.

Example:

```json
{
  "upstream": "job.import_123",
  "plugin.duplicate_detection": "job.plugin_456",
  "user.owner": "job.user_update_223"
}
```

The keys are exact attribute paths or path prefixes. The values are job/run identifiers.

Every automated attribute mutation should be represented by a job run. User edits can use direct user provenance.

The job run carries the automated provenance:

```text
job_runs
  id
  type
  state

  requested_by_type
  requested_by_id
  target_type
  target_id

  created_at
  updated_at
```

Example provenance records:

```text
run.import_123 | import_objects | upstream_event | bucket_123
run.extract_456 | extract_attributes | system | object_456
user.update_223 | user_attribute_update | user | user_123
```

Resolution rule:

1. Look for exact path provenance, such as `user.owner`.
2. If missing, walk up prefixes, such as `plugin.duplicate_detection`, then `plugin`.
3. If missing, fall back to object-level import or creation provenance if available.

This lets normal search query `objects.attributes`, while detail pages, audit views, and recomputation logic can answer where a value came from without creating one provenance row per object attribute.

Relations and collections should store provenance directly on their own rows.

Example:

```text
relations
  id
  source_object_id
  target_object_id
  relation_type

  created_by_type
  created_by_id
  created_by_name
  created_by_version
  created_by_job_id

  created_at
  updated_at
```

```text
collections
  id
  name
  query

  created_by_type
  created_by_id
  created_by_name
  created_by_version
  created_by_job_id

  created_at
  updated_at
```

This keeps provenance explicit without forcing every query to inspect audit logs.

## Rules

* Application code must go through the DB abstraction.
* Do not skip the abstraction for convenience.
* Keep DB-specific SQL isolated.
* Use Postgres features intentionally.
* Keep JSONB query construction centralized.
* Add generated columns or dedicated indexes only through the persistence layer.
* Keep attribute provenance in a compact JSONB sidecar, not in the hot JSONB attribute document.
* Do not create one provenance row per object attribute for the MVP.
* Test important persistence behavior against Postgres before calling an MVP complete.

## Initial Direction

Relic should require Postgres for local development and self-hosting.

Relic should start with JSONB attributes and GIN indexes.

Relic should postpone a dedicated search engine until Postgres JSONB queries become a real bottleneck.
