package storage

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/search"
)

func TestMutateObjectAttributesSetNestedAndDelete(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()
	seenAt := time.Now().UTC()

	created, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "attrs/user.jpg",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{"etag": "\"abc\""},
		},
		AttributeProvenance: ObjectAttributeProvenance{
			"upstream": "jobrun_sync",
		},
		SeenAt: &seenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	updated, err := objects.MutateObjectAttributes(ctx, created.ID, AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Sets: map[string]any{
			"user.owner":         "finance",
			"user.review.status": "approved",
		},
		Provenance: map[string]string{
			"user.owner":         "user_admin",
			"user.review.status": "user_admin",
		},
	})
	if err != nil {
		t.Fatalf("MutateObjectAttributes returned error: %v", err)
	}

	owner, ok := attributeValue(updated.Attributes, "user.owner")
	if !ok || owner != "finance" {
		t.Fatalf("user.owner = %#v, want finance", owner)
	}
	status, ok := attributeValue(updated.Attributes, "user.review.status")
	if !ok || status != "approved" {
		t.Fatalf("user.review.status = %#v, want approved", status)
	}
	if updated.AttributeProvenance["upstream"] != "jobrun_sync" {
		t.Fatalf("upstream provenance = %q, want preserved jobrun_sync", updated.AttributeProvenance["upstream"])
	}
	if updated.AttributeProvenance["user.owner"] != "user_admin" {
		t.Fatalf("user.owner provenance = %q, want user_admin", updated.AttributeProvenance["user.owner"])
	}

	catalog := store.AttributeCatalog()
	entry, ok, err := catalog.Resolve(ctx, "user.owner")
	if err != nil {
		t.Fatalf("Resolve user.owner returned error: %v", err)
	}
	if !ok || entry.Source != CatalogSourceObserved {
		t.Fatalf("user.owner catalog = %#v, want observed entry", entry)
	}

	deleted, err := objects.MutateObjectAttributes(ctx, created.ID, AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Deletes:       []string{"user.review.status"},
	})
	if err != nil {
		t.Fatalf("MutateObjectAttributes delete returned error: %v", err)
	}
	if _, ok := attributeValue(deleted.Attributes, "user.review.status"); ok {
		t.Fatal("user.review.status should be deleted")
	}
	if _, ok := deleted.AttributeProvenance["user.review.status"]; ok {
		t.Fatal("user.review.status provenance should be deleted")
	}
}

func TestMutateObjectAttributesSetSimpleUserPath(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()

	created, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "attrs/simple-user.jpg",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{"etag": "\"abc\""},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	updated, err := objects.MutateObjectAttributes(ctx, created.ID, AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Sets: map[string]any{
			"user.test": "hello",
		},
	})
	if err != nil {
		t.Fatalf("MutateObjectAttributes returned error: %v", err)
	}

	value, ok := attributeValue(updated.Attributes, "user.test")
	if !ok || value != "hello" {
		t.Fatalf("user.test = %#v, want hello", value)
	}
}

func TestMutateObjectAttributesRejectsNonUserPaths(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()

	created, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "attrs/reject.jpg",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{"etag": "\"abc\""},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	_, err = objects.MutateObjectAttributes(ctx, created.ID, AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Sets: map[string]any{
			"upstream.owner": "finance",
		},
	})
	if err == nil {
		t.Fatal("MutateObjectAttributes returned nil error for upstream path")
	}

	_, err = objects.MutateObjectAttributes(ctx, created.ID, AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Deletes:       []string{"upstream.etag"},
	})
	if err == nil {
		t.Fatal("MutateObjectAttributes returned nil error for upstream delete")
	}
}

func TestMutateObjectAttributesRejectsCatalogTypeConflict(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()
	catalog := store.AttributeCatalog()

	created, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "attrs/conflict.jpg",
		Attributes: ObjectAttributes{
			"user": map[string]any{"score": "high"},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	if err := catalog.UpsertObserved(ctx, "user.score", search.TypeString); err != nil {
		t.Fatalf("UpsertObserved returned error: %v", err)
	}

	_, err = objects.MutateObjectAttributes(ctx, created.ID, AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Sets: map[string]any{
			"user.score": 42,
		},
	})
	if !errors.Is(err, ErrCatalogTypeConflict) {
		t.Fatalf("MutateObjectAttributes error = %v, want %v", err, ErrCatalogTypeConflict)
	}
}

func TestMutateObjectAttributesMissingObject(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	_, err := store.Objects().MutateObjectAttributes(ctx, "object_missing", AttributeMutation{
		AllowedPrefix: UserAttributePrefix,
		Sets: map[string]any{
			"user.owner": "finance",
		},
	})
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("MutateObjectAttributes error = %v, want %v", err, ErrNotFound)
	}
}
