package storage

import (
	"context"
	"errors"
	"testing"
)

func TestCollectionStoreCreateGetListUpdateDelete(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	prepared, err := PrepareCollectionQuery(ctx, store.AttributeCatalog(), "FROM objects WHERE key = 'finance/report.pdf'")
	if err != nil {
		t.Fatalf("PrepareCollectionQuery returned error: %v", err)
	}

	collections := store.Collections()
	created, err := collections.CreateCollection(ctx, CreateCollectionParams{
		Name:          "Finance reports",
		Description:   "PDF reports owned by finance",
		QueryText:     "FROM objects WHERE key = 'finance/report.pdf'",
		QueryAST:      prepared.AST,
		QueryVersion:  prepared.QueryVersion,
		Dependencies:  DependenciesFromSearch(prepared.Dependencies),
		Status:        CollectionStatusValidEnum,
		CreatedByType: "user",
		CreatedByID:   "user_admin",
		OwnerUserID:   "user_admin",
	})
	if err != nil {
		t.Fatalf("CreateCollection returned error: %v", err)
	}
	if created.ID == "" {
		t.Fatal("expected collection id")
	}
	if created.Status != CollectionStatusValidEnum {
		t.Fatalf("Status = %q, want valid", created.Status)
	}
	if len(created.Dependencies) == 0 {
		t.Fatal("expected dependencies")
	}

	got, err := collections.GetCollection(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetCollection returned error: %v", err)
	}
	if got.Name != created.Name || got.QueryText != created.QueryText {
		t.Fatalf("GetCollection = %#v, want %#v", got, created)
	}

	listed, err := collections.ListCollections(ctx, ListCollectionsParams{})
	if err != nil {
		t.Fatalf("ListCollections returned error: %v", err)
	}
	if len(listed) != 1 {
		t.Fatalf("listed collections = %d, want 1", len(listed))
	}

	updatedQuery, err := PrepareCollectionQuery(ctx, store.AttributeCatalog(), "FROM objects WHERE key LIKE 'finance/%'")
	if err != nil {
		t.Fatalf("PrepareCollectionQuery for update returned error: %v", err)
	}
	queryText := "FROM objects WHERE key LIKE 'finance/%'"
	updated, err := collections.UpdateCollection(ctx, UpdateCollectionParams{
		ID:            created.ID,
		Name:          strPtr("Finance files"),
		Description:   strPtr("All finance keys"),
		QueryText:     &queryText,
		QueryAST:      updatedQuery.AST,
		QueryVersion:  &updatedQuery.QueryVersion,
		Dependencies:  DependenciesFromSearch(updatedQuery.Dependencies),
		Status:        collectionStatusPtr(CollectionStatusValidEnum),
		UpdateQuery:   true,
	})
	if err != nil {
		t.Fatalf("UpdateCollection returned error: %v", err)
	}
	if updated.Name != "Finance files" {
		t.Fatalf("Name = %q, want Finance files", updated.Name)
	}
	if updated.QueryText != queryText {
		t.Fatalf("QueryText = %q, want %q", updated.QueryText, queryText)
	}

	if err := collections.DeleteCollection(ctx, created.ID); err != nil {
		t.Fatalf("DeleteCollection returned error: %v", err)
	}
	if _, err := collections.GetCollection(ctx, created.ID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetCollection after delete error = %v, want ErrNotFound", err)
	}
}

func TestPrepareCollectionQueryRejectsInvalidRelicQL(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	_, err := PrepareCollectionQuery(ctx, store.AttributeCatalog(), "FROM buckets")
	if err == nil {
		t.Fatal("PrepareCollectionQuery returned nil error")
	}
}

func strPtr(value string) *string {
	return &value
}

func collectionStatusPtr(status CollectionStatus) *CollectionStatus {
	return &status
}
