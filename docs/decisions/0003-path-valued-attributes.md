# ADR 0003: Path-Valued Attributes and Attribute Catalog

## Status

Accepted

## Context

Pithosys treats object metadata as attributes: typed values addressed by dot-separated paths such as `upstream.size`, `user.owner`, and `extracted.mime_type`.

ADR 0001 chose Postgres with JSONB attribute documents on the object row. ADR 0002 chose PithosysQL as the search and collection contract, with binding against field and attribute definitions and compilation inside the storage layer.

PithosysQL, collections, and the UI all refer to attributes by path, but attribute **values** today live in a nested JSONB document per object. That is the right physical shape for sync-heavy buckets: one upsert per object, not one row per path per object.

At the same time, Pithosys needs a durable, typed view of which paths exist and what types they carry—for PithosysQL binding, editor autocomplete, validation, and collection invalidation. That metadata should not require users to maintain a schema by hand.

This ADR separates:

* **Logical model** — path + typed value
* **Value storage** — `objects.attributes` JSONB (unchanged from ADR 0001)
* **Type catalog** — `attribute_catalog` table, system-maintained

Pithosys explicitly does **not** introduce a row-per-path attribute table as part of this decision. A 1M-object bucket with ~25 paths per object would produce tens of millions of attribute rows and amplify sync write cost without a proven need. Row projections or external search indexes remain a future option if JSONB query performance becomes a bottleneck.

## Decision

Pithosys's attribute model is **path-valued** at the logical and API level: writers set and delete values by path; readers and PithosysQL refer to paths; nested JSON is how those paths are stored and returned on the object row.

Physical storage uses two concepts:

1. **Attribute values** — `objects.attributes` JSONB on the object row (source of truth for values).
2. **Attribute catalog** — `attribute_catalog` table (source of truth for path types used at bind time).

Provenance remains the compact `objects.attribute_provenance` JSON sidecar from ADR 0001.

### Logical model

Attribute mutations are expressed as path operations:

```text
Set(path, typed_value)
Delete(path)
SetProvenance(path_or_prefix, provenance_ref)
```

Storage may implement these by merging into the JSONB document. Callers do not patch JSON directly outside the storage layer.

Flattening rules when walking nested writer input:

* Nested maps become dot paths: `upstream.header.content_type`.
* Scalar leaves become catalog entries and JSONB leaves.
* Non-scalar JSON values (objects, arrays) are stored at the path in JSONB and cataloged as `json` when observed.

### Namespace write ownership

Write permission is enforced on **attribute namespace**, not job type.

Jobs are how work runs. Namespaces are where resulting metadata lives. Most jobs do not write attributes at all — for example `sync_bucket` orchestrates work, and `remove_objects` deletes catalog rows.

Only a small set of namespaces accept writes:

| Prefix | Writer | Examples |
| --- | --- | --- |
| `core.*` | system / storage | `core.object_id`, `core.first_seen_at`, `core.last_seen_at` |
| `upstream.*` | upstream catalog jobs | `sync_bucket`, `import_objects`, `refresh_objects` |
| `extracted.*` | `extract_attributes` job only | `extracted.mime_type`, `extracted.language` |
| `user.*` | user / API | `user.owner`, `user.review.status` |

Rules:

* Upstream-facing catalog jobs write **`upstream.*` only**, even though they run as jobs.
* Pithosys does **not** use a generic `job.<job_type>.*` write namespace. That pattern conflicts with upstream writes and implies every job type owns attribute paths when most do not.
* Other jobs (`detect_duplicates`, future enrichment) should prefer **relations**, collections, or events before adding new attribute namespaces. If a future job needs attributes, add a dedicated namespace in a new ADR — do not revive a generic job prefix.
* A mutation must not set or delete paths outside the caller's allowed namespace prefix.
* Provenance still records which job run wrote a namespace via `attribute_provenance`; provenance and write permission are separate concerns.

Example provenance sidecar:

```json
{
  "upstream": "run.sync_123",
  "extracted": "run.extract_456",
  "user.owner": "user.edit_789"
}
```

### Minimal object row

The `objects` table keeps only what Postgres needs for identity, scoping, and relational integrity. Everything else lives in `attributes` or `attribute_provenance`.

Top-level columns:

| Column | Why it stays |
| --- | --- |
| `id` | Primary key; relation and job targets |
| `bucket_id` | Foreign key; bucket scoping; cascade delete |
| `key` | Catalog identity within bucket; prefix indexes; upsert conflict target |
| `attributes` | All object metadata, including upstream and `core.*` lifecycle facts |
| `attribute_provenance` | Compact provenance sidecar |
| `created_at` / `updated_at` | Database bookkeeping for the catalog row, not object metadata |

Do **not** promote upstream or lifecycle metadata to top-level columns. Examples that belong in attributes:

| Was considered as column | Attribute path |
| --- | --- |
| `version_id` | `upstream.s3.version_id` (or upstream-specific namespace) |
| `first_seen_at` | `core.first_seen_at` |
| `last_seen_at` | `core.last_seen_at` |

Pithosys catalog identity is `(bucket_id, key)` — one active row per object key. Upstream version identifiers are evidence stored under `upstream.*`, not part of the Pithosys row key.

Storage injects and preserves `core.*` on upsert:

* `core.object_id` — stable Pithosys object id
* `core.first_seen_at` — preserved across updates
* `core.last_seen_at` — updated on every successful observation

Sync tombstone queries use `attributes #>> '{core,last_seen_at}'`, not a separate column.

Built-in PithosysQL fields remain limited to true catalog columns: `id`, `bucket_id`, `key`, `created_at`, `updated_at`. Upstream and core lifecycle paths are attributes.

### Physical schema

Object rows:

```sql
CREATE TABLE objects (
    id text PRIMARY KEY,
    bucket_id text NOT NULL REFERENCES buckets (id) ON DELETE CASCADE,
    key text NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    attribute_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT objects_attributes_is_object CHECK (jsonb_typeof(attributes) = 'object'),
    CONSTRAINT objects_attribute_provenance_is_object CHECK (jsonb_typeof(attribute_provenance) = 'object')
);

CREATE UNIQUE INDEX objects_bucket_key_idx ON objects (bucket_id, key);
CREATE INDEX objects_attributes_gin_idx ON objects USING gin (attributes);
CREATE INDEX objects_bucket_core_last_seen_at_idx ON objects (
    bucket_id,
    ((attributes #>> '{core,last_seen_at}')::timestamptz)
);
```

The attribute catalog is system-maintained:

```sql
CREATE TABLE attribute_catalog (
    path text PRIMARY KEY,
    value_type text NOT NULL,
    source text NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT attribute_catalog_source_valid CHECK (
        source IN ('builtin', 'registered', 'observed')
    ),
    CONSTRAINT attribute_catalog_value_type_valid CHECK (
        value_type IN ('string', 'integer', 'float', 'boolean', 'timestamp', 'json', 'unknown')
    )
);
```

Population rules:

* **`builtin`** — seeded from code for `core.*`, common `upstream.*`, and other stable platform paths. Never overridden by observed writes.
* **`registered`** — seeded from code for the `extracted.*` schema (and any future explicitly registered namespace). Never overridden by observed writes.
* **`observed`** — upserted automatically on every successful path mutation for paths not already defined in code. Expected for most `user.*` paths.

Conflict policy when an observed write disagrees with an existing catalog type:

* Widen numeric types (`integer` → `float`) and update catalog.
* Reject incompatible changes (`string` → `integer`) at mutation time.
* Mark dependent collections stale or invalid according to ADR 0002 when a type change affects saved queries.

Users do not edit `attribute_catalog` directly.

### Storage interfaces

Application code mutates attributes through storage repositories. Route handlers, workers, and jobs must not construct JSONB path SQL or patch attribute documents directly.

```go
type AttributeValue struct {
    Path string
    Type search.ValueType
    String    *string
    Integer   *int64
    Float     *float64
    Boolean   *bool
    Timestamp *time.Time
    JSON      json.RawMessage
}

type AttributeMutation struct {
    AllowedPrefix string // e.g. "upstream", "extracted", "user"
    Sets          []AttributeValue
    Deletes       []string
    Provenance    map[string]string // path or prefix -> provenance ref
}

type AttributeCatalogStore interface {
    Resolve(ctx context.Context, path string) (search.AttributeDefinition, bool)
    List(ctx context.Context) ([]search.AttributeDefinition, error)
    ObservePaths(ctx context.Context, paths []AttributeValue) error
}

type CatalogRegistry struct {
    catalog AttributeCatalogStore
    builtin search.Registry
}

// CatalogRegistry implements search.Registry:
// builtin + registered catalog entries, then observed paths, then unknown fallback.
```

Object upsert/sync flows may still accept nested attribute maps from upstream adapters. Storage flattens scalars for catalog observation and merges values into `objects.attributes`.

PithosysQL execution:

```go
type SearchStore interface {
    Validate(ctx context.Context, text string) (search.BoundQuery, error)
    Execute(ctx context.Context, bound search.BoundQuery, scope SearchScope) ([]Object, error)
}
```

`Validate` uses `CatalogRegistry`. `Execute` compiles against `objects.attributes` JSONB and object columns. JSONB path construction and typed casts stay inside `packages/storage`.

### Relationship to PithosysQL

PithosysQL bind semantics from ADR 0002 are unchanged:

* Parse → Bind against registry → record dependencies → compile → execute.

The registry implementation becomes:

```text
CatalogRegistry = BuiltinRegistry + attribute_catalog (+ unknown fallback)
```

The compiler reads types from the catalog and emits parameterized JSONB predicates:

```sql
-- example: integer comparison on a cataloged path
(objects.attributes #>> '{upstream,size}')::bigint >= $1

-- example: unknown path, equality only
objects.attributes #>> '{user,owner}' = $1
```

Saved collections continue to store query text, AST, dependencies, and status. They do not store compiled SQL.

### Catalog observation on write

On every attribute mutation, storage:

1. Validates namespace ownership.
2. Merges sets and deletes into `objects.attributes`.
3. Updates provenance sidecar when provided.
4. Flattens affected paths and upserts `attribute_catalog` for paths not already defined as `builtin` or `registered`.

Type inference for observed paths uses the logical value being written, not a later scan of existing JSONB.

Example mutation:

```json
{
  "upstream": {
    "size": 1048576,
    "header": { "content_type": "image/jpeg" }
  }
}
```

Catalog upserts:

```text
upstream.size → integer (observed)
upstream.header.content_type → string (observed)
```

If `upstream.size` is already `builtin`, the catalog row is left unchanged.

## Future options (out of scope)

If JSONB search becomes a proven bottleneck, Pithosys may add without changing the logical model:

* Generated columns or partial indexes on hot JSONB paths
* An async row projection for selected paths only
* An external search engine fed from object rows

Those are optimizations. They are not required to adopt path-valued mutations or the attribute catalog.

## Consequences

This gives Pithosys:

* Path-based semantics for PithosysQL, mutations, and collections without row-per-path write amplification.
* Auto-maintained typing for bind, validate, autocomplete, and collection invalidation.
* Sync-friendly storage: one object row upsert per catalog object, not millions of attribute rows.
* Continuity with ADR 0001 JSONB as the value store and query substrate for the MVP.

This also costs Pithosys:

* JSONB query compilation still requires careful casts and index discipline.
* Catalog and JSONB values can drift if mutations bypass storage; the abstraction must be enforced.
* Very large-scale search may eventually need projections or a dedicated search engine anyway.

## Package boundaries

`packages/search` owns path syntax, AST, bind rules, dependency types, and the `Registry` interface. It does not know about JSONB operators or the catalog table.

`packages/storage` owns:

* Path-based mutation merging into `objects.attributes`
* `AttributeCatalogStore` and `CatalogRegistry`
* Catalog upsert on mutation
* Namespace enforcement
* PithosysQL compilation to SQL over `objects` and JSONB
* Centralized JSONB path and cast construction

`packages/upstreams` and job packages produce nested attribute maps. They do not write Postgres directly.

`apps/api` and `apps/worker` call object repositories through storage mutations, not ad hoc JSONB SQL.

## Rules

* Treat **path + typed value** as the logical attribute atom.
* Keep **values** in `objects.attributes` JSONB.
* Keep **types** in `attribute_catalog`, auto-maintained on mutation.
* Resolve PithosysQL against `CatalogRegistry`; builtin and registered definitions beat observed catalog entries.
* Compile and execute search only inside `packages/storage`.
* Do not store compiled SQL on saved collections.
* Enforce namespace write ownership by prefix on every mutation; do not model this as one namespace per job type.
* Do not leak JSONB path operators into `packages/search`, API handlers, or workers.
* Do not introduce row-per-path attribute storage without a new ADR and measured need.

## Relationship to prior ADRs

This ADR **extends** ADR 0001 and ADR 0002. It does not supersede JSONB value storage.

ADR 0001 remains the source of truth for:

* Postgres as the database
* JSONB attribute documents on the object row
* GIN indexing over attributes
* Compact provenance sidecars

ADR 0002 remains the source of truth for PithosysQL parse, bind, dependencies, and collection semantics.

## Initial implementation order

1. Add migration for `attribute_catalog`.
2. Seed catalog from builtin definitions aligned with `packages/search`.
3. Implement catalog upsert on object attribute writes in `packages/storage`.
4. Implement `CatalogRegistry` for PithosysQL bind and validate endpoints.
5. Implement PithosysQL compilation against `objects.attributes` using catalog types for casts.
6. Optionally backfill `attribute_catalog` from existing object JSONB in a one-off job.
