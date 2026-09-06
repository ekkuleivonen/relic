package storage

import (
	"strings"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/search"
)

func TestCompileObjectsSearchStep1FieldPredicate(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, "FROM objects WHERE key = 'foo.txt'", SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.key = $1`,
		Args: []any{"foo.txt"},
	})
}

func TestCompileObjectsSearchStep2TypedAttributeComparison(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('upstream.size') >= 1048576
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE (objects.attributes #>> '{upstream,size}')::bigint >= $1`,
		Args: []any{int64(1048576)},
	})
}

func TestCompileObjectsSearchStep3StringAttributeLike(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('upstream.header.content_type') LIKE 'image/%'
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.attributes #>> '{upstream,header,content_type}' LIKE $1`,
		Args: []any{"image/%"},
	})
}

func TestCompileObjectsSearchStep4TimestampAttributeRange(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('upstream.last_modified') >= timestamp '2026-06-26T00:00:00Z'
		  AND attr('upstream.last_modified') <= timestamp '2026-06-27T00:00:00Z'
	`, SearchScope{})

	wantTimeLower := mustTimestamp("2026-06-26T00:00:00Z")
	wantTimeUpper := mustTimestamp("2026-06-27T00:00:00Z")

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE (objects.attributes #>> '{upstream,last_modified}')::timestamptz >= $1 AND (objects.attributes #>> '{upstream,last_modified}')::timestamptz <= $2`,
		Args: []any{wantTimeLower, wantTimeUpper},
	})
}

func TestCompileObjectsSearchStep5NullInBetween(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('user.owner') IS NULL
		  AND attr('upstream.size') IN (1024, 4096)
		  AND attr('upstream.size') BETWEEN 1024 AND 4096
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.attributes #>> '{user,owner}' IS NULL AND (objects.attributes #>> '{upstream,size}')::bigint IN ($1, $2) AND (objects.attributes #>> '{upstream,size}')::bigint BETWEEN $3 AND $4`,
		Args: []any{int64(1024), int64(4096), int64(1024), int64(4096)},
	})
}

func TestCompileObjectsSearchStep6BooleanLogic(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('upstream.header.content_type') = 'image/jpeg'
		  AND (attr('upstream.size') >= 1024 OR NOT attr('user.archived') = true)
	`, SearchScope{}, registryWithAttributes(search.AttributeDefinition{Path: "user.archived", Type: search.TypeBoolean}))

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.attributes #>> '{upstream,header,content_type}' = $1 AND ((objects.attributes #>> '{upstream,size}')::bigint >= $2 OR NOT ((objects.attributes #>> '{user,archived}')::boolean = $3))`,
		Args: []any{"image/jpeg", int64(1024), true},
	})
}

func TestCompileObjectsSearchStep7OrderBy(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE key = 'photos/a.jpg'
		ORDER BY attr('upstream.last_modified') DESC, key ASC
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.key = $1
ORDER BY (objects.attributes #>> '{upstream,last_modified}')::timestamptz DESC, objects.key ASC`,
		Args: []any{"photos/a.jpg"},
	})
}

func TestCompileObjectsSearchStep8LimitOffset(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE key = 'photos/a.jpg'
		LIMIT 100 OFFSET 20
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.key = $1
LIMIT $2
OFFSET $3`,
		Args: []any{"photos/a.jpg", int64(100), int64(20)},
	})
}

func TestCompileObjectsSearchStep9ScopeBucketID(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('upstream.size') >= 1048576
	`, SearchScope{BucketID: "bucket_abc"})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.bucket_id = $1 AND (objects.attributes #>> '{upstream,size}')::bigint >= $2`,
		Args: []any{"bucket_abc", int64(1048576)},
	})
}

func TestCompileObjectsSearchBucketPredicate(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE bucket('production')
		  AND attr('upstream.size') >= 1048576
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE objects.bucket_id = (
	SELECT b.id
	FROM buckets b
	WHERE b.name = $1
	LIMIT 1
) AND (objects.attributes #>> '{upstream,size}')::bigint >= $2`,
		Args: []any{"production", int64(1048576)},
	})
}

func TestCompileObjectsSearchStep10RelationExists(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE has_relation('duplicate')
		  AND NOT has_relation('thumbnail_of', 'in')
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE EXISTS (
	SELECT 1
	FROM relations r
	WHERE (r.source_object_id = objects.id OR r.target_object_id = objects.id)
		AND r.relation_type = $1
) AND NOT (EXISTS (
	SELECT 1
	FROM relations r
	WHERE r.target_object_id = objects.id
		AND r.relation_type = $2
))`,
		Args: []any{"duplicate", "thumbnail_of"},
	})
}

func TestCompileObjectsSearchRelativeTimestamp(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('core.last_seen_at') >= now() - interval '7 days'
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE (objects.attributes #>> '{core,last_seen_at}')::timestamptz >= (now() - interval '7 days')`,
		Args: []any{},
	})
}

func TestCompileObjectsSearchExplicitAttributeCast(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('user.score')::integer >= 100
	`, SearchScope{})

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE (objects.attributes #>> '{user,score}')::bigint >= $1`,
		Args: []any{int64(100)},
	})
}

func TestCompileObjectsSearchDateLiteralAndStringDateCast(t *testing.T) {
	compiled := mustCompileObjectsSearch(t, `
		FROM objects
		WHERE attr('upstream.last_modified') >= date '2026-06-26'
		  AND attr('upstream.last_modified') < '2026-06-27'::date
	`, SearchScope{})

	wantLower := mustTimestamp("2026-06-26T00:00:00Z")
	wantUpper := mustTimestamp("2026-06-27T00:00:00Z")

	assertCompiledQuery(t, compiled, CompiledQuery{
		SQL: strings.TrimSpace(objectsSearchSelectSQL) + `
WHERE (objects.attributes #>> '{upstream,last_modified}')::timestamptz >= $1 AND (objects.attributes #>> '{upstream,last_modified}')::timestamptz < $2`,
		Args: []any{wantLower, wantUpper},
	})
}

func TestCompileObjectsSearchRejectsUnsupportedTarget(t *testing.T) {
	bound := mustBindPithosysQL(t, "FROM relations", search.BuiltinRegistry())
	_, err := CompileObjectsSearch(bound, SearchScope{})
	if err == nil {
		t.Fatal("CompileObjectsSearch returned nil error")
	}
}

func mustCompileObjectsSearch(t *testing.T, pithosysql string, scope SearchScope, registries ...search.Registry) CompiledQuery {
	t.Helper()

	var registry search.Registry = search.BuiltinRegistry()
	if len(registries) > 0 && registries[0] != nil {
		registry = registries[0]
	}

	bound := mustBindPithosysQL(t, pithosysql, registry)
	compiled, err := CompileObjectsSearch(bound, scope)
	if err != nil {
		t.Fatalf("CompileObjectsSearch returned error: %v", err)
	}

	return compiled
}

func mustBindPithosysQL(t *testing.T, pithosysql string, registry search.Registry) search.BoundQuery {
	t.Helper()

	query, err := search.Parse(pithosysql)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	bound, err := search.Bind(query, registry)
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	return bound
}

func registryWithAttributes(attributes ...search.AttributeDefinition) search.Registry {
	return search.NewStaticRegistry(search.BuiltinTargetDefinitions(), append(search.BuiltinAttributeDefinitions(), attributes...))
}

func assertCompiledQuery(t *testing.T, got CompiledQuery, want CompiledQuery) {
	t.Helper()

	if got.SQL != want.SQL {
		t.Fatalf("SQL mismatch (-got +want):\n-got\n%s\n-want\n%s", got.SQL, want.SQL)
	}

	if len(got.Args) != len(want.Args) {
		t.Fatalf("args length = %d, want %d; got=%#v want=%#v", len(got.Args), len(want.Args), got.Args, want.Args)
	}
	for index := range want.Args {
		gotArg := got.Args[index]
		wantArg := want.Args[index]
		switch wantTyped := wantArg.(type) {
		case time.Time:
			gotTyped, ok := gotArg.(time.Time)
			if !ok || !gotTyped.Equal(wantTyped) {
				t.Fatalf("args[%d] = %#v, want %#v", index, gotArg, wantArg)
			}
		default:
			if gotArg != wantArg {
				t.Fatalf("args[%d] = %#v, want %#v", index, gotArg, wantArg)
			}
		}
	}
}

func mustTimestamp(value string) time.Time {
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		panic(err)
	}

	return parsed.UTC()
}
