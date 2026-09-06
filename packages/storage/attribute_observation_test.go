package storage

import (
	"context"
	"testing"

	"github.com/elei-io/pithosys/packages/search"
)

func TestFlattenObjectAttributes(t *testing.T) {
	paths := flattenObjectAttributes(ObjectAttributes{
		"upstream": map[string]any{
			"size": 1048576,
			"header": map[string]any{
				"content_type": "image/jpeg",
			},
		},
		"user": map[string]any{
			"owner": "finance",
		},
	})

	want := map[string]search.ValueType{
		"upstream.size":                  search.TypeInteger,
		"upstream.header.content_type":   search.TypeString,
		"user.owner":                     search.TypeString,
	}

	for path, typ := range want {
		got, ok := paths[path]
		if !ok {
			t.Fatalf("missing flattened path %q", path)
		}
		if got != typ {
			t.Fatalf("path %q type = %q, want %q", path, got, typ)
		}
	}
}

func TestInferCatalogValueTypeTimestamp(t *testing.T) {
	typ, ok := inferCatalogValueType("2026-06-26T00:00:00Z")
	if !ok {
		t.Fatal("inferCatalogValueType returned false")
	}
	if typ != search.TypeTimestamp {
		t.Fatalf("type = %q, want %q", typ, search.TypeTimestamp)
	}
}

func TestObserveAttributeCatalogOnUpsert(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	_, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
		Attributes: ObjectAttributes{
			"user": map[string]any{
				"owner": "finance",
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	entry, ok, err := store.AttributeCatalog().Resolve(ctx, "user.owner")
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false for observed path")
	}
	if entry.Source != CatalogSourceObserved {
		t.Fatalf("source = %q, want %q", entry.Source, CatalogSourceObserved)
	}
	if entry.ValueType != search.TypeString {
		t.Fatalf("value type = %q, want %q", entry.ValueType, search.TypeString)
	}

	userPrefix, ok, err := store.AttributeCatalog().Resolve(ctx, "user")
	if err != nil {
		t.Fatalf("Resolve user returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false for user prefix path")
	}
	if userPrefix.ValueType != search.TypeUnknown {
		t.Fatalf("user value type = %q, want %q", userPrefix.ValueType, search.TypeUnknown)
	}
}

func TestObserveAttributeCatalogRegistersNestedUserPaths(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	_, err := store.Objects().MutateObjectAttributes(ctx, mustCreateNestedUserAttributeObject(t, ctx, store, bucket.ID), AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Sets: map[string]any{
			"user.review.status": "approved",
		},
	})
	if err != nil {
		t.Fatalf("MutateObjectAttributes returned error: %v", err)
	}

	for _, path := range []string{"user.review.status", "user.review", "user"} {
		entry, ok, err := store.AttributeCatalog().Resolve(ctx, path)
		if err != nil {
			t.Fatalf("Resolve %q returned error: %v", path, err)
		}
		if !ok {
			t.Fatalf("Resolve returned false for %q", path)
		}
		if entry.Source != CatalogSourceObserved {
			t.Fatalf("%q source = %q, want %q", path, entry.Source, CatalogSourceObserved)
		}
		if path != "user.review.status" && entry.ValueType != search.TypeUnknown {
			t.Fatalf("%q value type = %q, want %q", path, entry.ValueType, search.TypeUnknown)
		}
	}

	status, ok, err := store.AttributeCatalog().Resolve(ctx, "user.review.status")
	if err != nil {
		t.Fatalf("Resolve user.review.status returned error: %v", err)
	}
	if !ok || status.ValueType != search.TypeString {
		t.Fatalf("user.review.status = %#v, want observed string", status)
	}
}

func mustCreateNestedUserAttributeObject(t *testing.T, ctx context.Context, store *Store, bucketID string) string {
	t.Helper()

	object, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucketID,
		Key:      "attrs/nested-user.jpg",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{"etag": "\"abc\""},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	return object.ID
}

func TestValidatePithosysQL(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	bound, err := ValidatePithosysQL(ctx, store.AttributeCatalog(), `
		FROM objects
		WHERE attr('upstream.size') >= 1048576
	`)
	if err != nil {
		t.Fatalf("ValidatePithosysQL returned error: %v", err)
	}
	if bound.Query.From != search.TargetObjects {
		t.Fatalf("from = %q, want objects", bound.Query.From)
	}
	if len(bound.Dependencies) == 0 {
		t.Fatal("dependencies are empty")
	}
}

func TestBuildSearchRegistryUsesCatalog(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.UpsertObserved(ctx, "user.owner", search.TypeString); err != nil {
		t.Fatalf("UpsertObserved returned error: %v", err)
	}

	registry, err := BuildSearchRegistry(ctx, catalog)
	if err != nil {
		t.Fatalf("BuildSearchRegistry returned error: %v", err)
	}

	definition, ok := registry.ResolveAttribute("user.owner")
	if !ok {
		t.Fatal("ResolveAttribute returned false for catalog path")
	}
	if definition.Type != search.TypeString {
		t.Fatalf("type = %q, want string", definition.Type)
	}
}
