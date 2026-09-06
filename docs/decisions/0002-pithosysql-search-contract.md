# ADR 0002: Use PithosysQL as the Search and Collection Query Contract

## Status

Accepted

## Context

Pithosys's search surface is not only an object list filter.

Search will eventually support:

* Interactive object discovery.
* Stored collections.
* Duplicate detection jobs.
* Attribute-driven workflows.
* Cross-bucket inventory views.
* Future relation, event, and governance queries.

The manifest describes collections as saved searches and recommends avoiding a new query language unless there is a clear need. At the same time, storing raw Postgres SQL as the durable collection contract would expose Pithosys's physical storage layout, make permission checks harder, and couple saved collections to current JSONB implementation details.

Pithosys needs a query contract that is close enough to SQL to feel familiar and work well in an editor, but constrained enough that the backend can validate and compile it safely.

## Decision

Pithosys will introduce **PithosysQL v1**, a SQL-shaped query language over Pithosys primitives.

The frontend may treat PithosysQL as text and provide an editor experience with Postgres-like syntax highlighting, autocomplete, and linting.

The backend will never execute PithosysQL text directly.

Backend execution flow:

1. Parse PithosysQL text into a canonical AST.
2. Bind and validate the AST against Pithosys's current field and attribute definitions.
3. Record query dependencies.
4. Compile the bound query to parameterized storage queries.
5. Execute only the generated parameterized query.

PithosysQL v1 starts with objects:

```sql
FROM objects
WHERE attr('upstream.size') >= 1048576
  AND attr('upstream.header.content_type') = 'application/pdf'
ORDER BY attr('upstream.last_modified') DESC
LIMIT 100
```

Saved collections should store the authoring text, canonical AST, and bound dependency metadata:

```json
{
  "query_text": "FROM objects WHERE attr('user.owner') = 'finance'",
  "query_ast": {
    "version": "pithosysql.v1",
    "from": "objects",
    "where": {
      "op": "eq",
      "left": { "attr": "user.owner" },
      "right": { "string": "finance" }
    }
  },
  "query_version": "pithosysql.v1",
  "dependencies": [
    {
      "kind": "attribute",
      "path": "user.owner",
      "type": "string"
    }
  ],
  "status": "valid"
}
```

The query text is the editable authoring form.

The AST is the parsed syntax form.

The bound dependencies are the view-like contract Pithosys uses to validate, invalidate, refresh, and explain collections.

## Collections As Managed Views

Pithosys collections are managed views over Pithosys primitives.

The default collection mode is virtual:

* Pithosys stores the query definition.
* Collection reads execute the current valid query.
* Membership is derived, not manually maintained.

Future materialized collections may cache membership:

```text
collection_objects
  collection_id
  object_id
  matched_at
  query_version
```

In that mode, collections behave like materialized views:

* Object, attribute, relation, or definition changes can mark a collection stale.
* Background jobs can refresh stale materialized membership.
* The query definition remains the source of truth.

Collections are allowed to become invalid when their dependencies change.

Examples:

* A referenced attribute definition is deleted.
* An attribute changes from `integer` to `string`.
* A future relation type used by a collection is removed or redefined.

This is expected. Collections should fail like schema-bound database views, not like ad hoc runtime queries. Pithosys should know what a collection depends on and explain why it is invalid or stale.

## Relationships

Object relationships should become queryable facts in PithosysQL.

Future syntax may look like:

```sql
FROM objects
WHERE EXISTS relation(type = 'duplicate')
```

or a more Pithosys-specific helper:

```sql
FROM objects
WHERE has_relation('duplicate')
```

The exact syntax is deferred, but the dependency model is not.

Relationship-aware collections should record dependencies on relation types, just as attribute-aware collections record dependencies on attribute definitions:

```json
{
  "kind": "relation_type",
  "name": "duplicate"
}
```

If a relation type is removed, renamed, or redefined, collections that depend on it may become invalid or stale.

In Postgres, relation predicates will likely compile to `EXISTS` queries against a relations table:

```sql
WHERE EXISTS (
  SELECT 1
  FROM relations r
  WHERE r.source_object_id = objects.id
    AND r.relation_type = 'duplicate'
)
```

This reinforces the need for a bound query and dependency layer. Search cannot be only a JSONB object-attribute filter forever; it must be able to bind fields, attributes, relations, and eventually collections as first-class query dependencies.

## Initial Scope

PithosysQL v1 initially supports:

* `FROM objects`.
* `WHERE` boolean predicates.
* Built-in object fields such as `bucket_id`, `key`, `id`, `created_at`, and `updated_at`.
* Attribute references through `attr('path.to.attribute')`.
* Operators such as `=`, `!=`, `<`, `<=`, `>`, `>=`, `LIKE`, `IN`, `BETWEEN`, `IS NULL`, and `IS NOT NULL`.
* `AND`, `OR`, and `NOT`.
* `ORDER BY`.
* `LIMIT`.

The first implementation may support only a subset of those features, but the package and tests should grow toward this model.

## Package Boundaries

`packages/search` owns:

* PithosysQL AST types.
* Text parsing.
* AST binding and validation.
* Field and attribute definition registry interfaces.
* Bound query and dependency models.
* Canonical serialization rules.
* Parser, binding, and validation tests.
* Future relation reference binding rules.

`packages/storage` owns:

* Compiling validated and bound PithosysQL queries to Postgres queries.
* JSONB path handling.
* Parameter binding.
* Index-aware storage optimizations.

`apps/api` owns:

* Search HTTP request and response shapes.
* Parse and validation error presentation.
* Calling storage through the database abstraction.

`apps/web` owns:

* PithosysQL editor UI.
* Autocomplete and linting integration.
* Query builder affordances that produce PithosysQL text or ASTs.

Collections own:

* Stored query text.
* Stored query AST.
* Stored dependency metadata.
* Validity and materialization status.
* Future relation-type dependency tracking.

## Consequences

This gives Pithosys:

* A single query model for search, saved collections, jobs, and future workflows.
* A SQL-like user experience without exposing raw SQL execution.
* A view-like model where stored collections can be validated, invalidated, and refreshed.
* A safe path to CodeMirror syntax highlighting and autocomplete.
* A clean boundary between product semantics and Postgres JSONB details.

This also costs Pithosys:

* A parser and validator must be maintained.
* PithosysQL behavior must be documented and tested.
* Query features need careful versioning as saved collections become durable product data.
* Attribute and field definitions become schema-like dependencies for collections.
* Collection invalidation and refresh behavior must be explicit once collections are persisted.

## Rules

* Do not execute PithosysQL text directly.
* Do not store only raw query text for saved collections.
* Keep AST parsing and validation free of database dependencies.
* Bind collection queries against explicit field and attribute definitions.
* Treat relation types as schema-like dependencies once relation predicates exist.
* Store enough dependency metadata to explain invalid or stale collections.
* Keep Postgres-specific compilation inside the storage layer.
* Version the query language before storing collection queries.
* Prefer a small SQL-shaped subset over a large, weakly specified language.
