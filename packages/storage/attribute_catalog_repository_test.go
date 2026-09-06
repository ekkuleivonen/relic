package storage

import (
	"context"
	"errors"
	"testing"

	"github.com/elei-io/pithosys/packages/search"
)

func TestAttributeCatalogStoreSeedAndResolve(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.SeedBuiltin(ctx, search.BuiltinAttributeDefinitions()); err != nil {
		t.Fatalf("SeedBuiltin returned error: %v", err)
	}

	entry, ok, err := catalog.Resolve(ctx, "upstream.size")
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false for seeded path")
	}
	if entry.Source != CatalogSourceBuiltin {
		t.Fatalf("source = %q, want %q", entry.Source, CatalogSourceBuiltin)
	}
	if entry.ValueType != search.TypeInteger {
		t.Fatalf("value type = %q, want %q", entry.ValueType, search.TypeInteger)
	}
}

func TestAttributeCatalogStoreList(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := SeedAttributeCatalog(ctx, catalog); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	entries, err := catalog.List(ctx)
	if err != nil {
		t.Fatalf("List returned error: %v", err)
	}
	if len(entries) != (len(search.BuiltinAttributeDefinitions()) + len(search.RegisteredAttributeDefinitions())) {
		t.Fatalf("list length = %d, want %d", len(entries), (len(search.BuiltinAttributeDefinitions()) + len(search.RegisteredAttributeDefinitions())))
	}
}

func TestAttributeCatalogStoreSeedRegistered(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.SeedRegistered(ctx, []search.AttributeDefinition{
		{Path: "extracted.mime_type", Type: search.TypeString},
	}); err != nil {
		t.Fatalf("SeedRegistered returned error: %v", err)
	}

	entry, ok, err := catalog.Resolve(ctx, "extracted.mime_type")
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false for registered path")
	}
	if entry.Source != CatalogSourceRegistered {
		t.Fatalf("source = %q, want %q", entry.Source, CatalogSourceRegistered)
	}
}

func TestAttributeCatalogStoreUpsertObserved(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.SeedBuiltin(ctx, []search.AttributeDefinition{
		{Path: "upstream.size", Type: search.TypeInteger},
	}); err != nil {
		t.Fatalf("SeedBuiltin returned error: %v", err)
	}

	if err := catalog.UpsertObserved(ctx, "user.owner", search.TypeString); err != nil {
		t.Fatalf("UpsertObserved returned error: %v", err)
	}

	entry, ok, err := catalog.Resolve(ctx, "user.owner")
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
}

func TestAttributeCatalogStoreUpsertObservedNoopOnBuiltin(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.SeedBuiltin(ctx, []search.AttributeDefinition{
		{Path: "upstream.size", Type: search.TypeInteger},
	}); err != nil {
		t.Fatalf("SeedBuiltin returned error: %v", err)
	}

	if err := catalog.UpsertObserved(ctx, "upstream.size", search.TypeString); err != nil {
		t.Fatalf("UpsertObserved returned error: %v", err)
	}

	entry, ok, err := catalog.Resolve(ctx, "upstream.size")
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false for builtin path")
	}
	if entry.Source != CatalogSourceBuiltin {
		t.Fatalf("source = %q, want %q", entry.Source, CatalogSourceBuiltin)
	}
	if entry.ValueType != search.TypeInteger {
		t.Fatalf("value type = %q, want %q", entry.ValueType, search.TypeInteger)
	}
}

func TestAttributeCatalogStoreUpsertObservedWidensIntegerToFloat(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.UpsertObserved(ctx, "user.score", search.TypeInteger); err != nil {
		t.Fatalf("UpsertObserved integer returned error: %v", err)
	}
	if err := catalog.UpsertObserved(ctx, "user.score", search.TypeFloat); err != nil {
		t.Fatalf("UpsertObserved float returned error: %v", err)
	}

	entry, ok, err := catalog.Resolve(ctx, "user.score")
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false")
	}
	if entry.ValueType != search.TypeFloat {
		t.Fatalf("value type = %q, want %q", entry.ValueType, search.TypeFloat)
	}
}

func TestAttributeCatalogStoreUpsertObservedRejectsTypeConflict(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.UpsertObserved(ctx, "user.owner", search.TypeString); err != nil {
		t.Fatalf("UpsertObserved string returned error: %v", err)
	}

	err := catalog.UpsertObserved(ctx, "user.owner", search.TypeInteger)
	if !errors.Is(err, ErrCatalogTypeConflict) {
		t.Fatalf("UpsertObserved error = %v, want %v", err, ErrCatalogTypeConflict)
	}
}

func TestAttributeCatalogStoreSeedDoesNotOverwriteObserved(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	catalog := store.AttributeCatalog()
	if err := catalog.UpsertObserved(ctx, "user.owner", search.TypeString); err != nil {
		t.Fatalf("UpsertObserved returned error: %v", err)
	}

	if err := catalog.SeedBuiltin(ctx, []search.AttributeDefinition{
		{Path: "user.owner", Type: search.TypeInteger},
	}); err != nil {
		t.Fatalf("SeedBuiltin returned error: %v", err)
	}

	entry, ok, err := catalog.Resolve(ctx, "user.owner")
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false")
	}
	if entry.Source != CatalogSourceObserved {
		t.Fatalf("source = %q, want observed to remain", entry.Source)
	}
	if entry.ValueType != search.TypeString {
		t.Fatalf("value type = %q, want observed string to remain", entry.ValueType)
	}
}

func TestSeedAttributeCatalog(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	entry, ok, err := store.AttributeCatalog().Resolve(ctx, "core.object_id")
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !ok {
		t.Fatal("Resolve returned false for builtin core path")
	}
	if entry.Source != CatalogSourceBuiltin {
		t.Fatalf("source = %q, want %q", entry.Source, CatalogSourceBuiltin)
	}
}
