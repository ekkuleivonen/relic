package storage

import (
	"context"
	"errors"
	"fmt"
	"testing"
)

func TestObjectStoreCountObjectsInScope(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()

	for _, key := range []string{"photos/a.jpg", "photos/b.jpg", "docs/readme.md"} {
		if _, err := objects.UpsertObject(ctx, UpsertObjectParams{
			BucketID: bucket.ID,
			Key:      key,
		}); err != nil {
			t.Fatalf("UpsertObject %q returned error: %v", key, err)
		}
	}

	allCount, err := objects.CountObjectsInScope(ctx, ObjectScopeParams{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("CountObjectsInScope all returned error: %v", err)
	}
	if allCount != 3 {
		t.Fatalf("all count = %d, want 3", allCount)
	}

	photosCount, err := objects.CountObjectsInScope(ctx, ObjectScopeParams{
		BucketID: bucket.ID,
		Prefix:   "photos/",
	})
	if err != nil {
		t.Fatalf("CountObjectsInScope photos returned error: %v", err)
	}
	if photosCount != 2 {
		t.Fatalf("photos count = %d, want 2", photosCount)
	}

	emptyCount, err := objects.CountObjectsInScope(ctx, ObjectScopeParams{
		BucketID: bucket.ID,
		Prefix:   "missing/",
	})
	if err != nil {
		t.Fatalf("CountObjectsInScope missing returned error: %v", err)
	}
	if emptyCount != 0 {
		t.Fatalf("missing count = %d, want 0", emptyCount)
	}
}

func TestObjectStoreCountObjectsInScopeEmptyBucket(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)

	count, err := store.Objects().CountObjectsInScope(ctx, ObjectScopeParams{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("CountObjectsInScope returned error: %v", err)
	}
	if count != 0 {
		t.Fatalf("count = %d, want 0", count)
	}
}

func TestObjectStoreStreamObjectsInScope(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()

	keys := []string{"photos/a.jpg", "photos/b.jpg", "docs/readme.md"}
	for _, key := range keys {
		if _, err := objects.UpsertObject(ctx, UpsertObjectParams{
			BucketID: bucket.ID,
			Key:      key,
		}); err != nil {
			t.Fatalf("UpsertObject %q returned error: %v", key, err)
		}
	}

	var streamed []Object
	if err := objects.StreamObjectsInScope(ctx, ObjectScopeParams{
		BucketID: bucket.ID,
		Prefix:   "photos/",
	}, func(object Object) error {
		streamed = append(streamed, object)
		return nil
	}); err != nil {
		t.Fatalf("StreamObjectsInScope returned error: %v", err)
	}

	if len(streamed) != 2 {
		t.Fatalf("streamed length = %d, want 2", len(streamed))
	}
	if streamed[0].Key != "photos/a.jpg" || streamed[1].Key != "photos/b.jpg" {
		t.Fatalf("streamed keys = %q, %q; want photos order", streamed[0].Key, streamed[1].Key)
	}
}

func TestObjectStoreStreamObjectsInScopeMatchesListObjectsInScope(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()
	scope := ObjectScopeParams{BucketID: bucket.ID}

	for _, key := range []string{"alpha.txt", "beta.txt", "nested/gamma.txt"} {
		if _, err := objects.UpsertObject(ctx, UpsertObjectParams{
			BucketID: bucket.ID,
			Key:      key,
		}); err != nil {
			t.Fatalf("UpsertObject %q returned error: %v", key, err)
		}
	}

	listed, err := objects.ListObjectsInScope(ctx, scope)
	if err != nil {
		t.Fatalf("ListObjectsInScope returned error: %v", err)
	}

	var streamed []Object
	if err := objects.StreamObjectsInScope(ctx, scope, func(object Object) error {
		streamed = append(streamed, object)
		return nil
	}); err != nil {
		t.Fatalf("StreamObjectsInScope returned error: %v", err)
	}

	if len(streamed) != len(listed) {
		t.Fatalf("streamed length = %d, want listed length %d", len(streamed), len(listed))
	}
	for i := range listed {
		if streamed[i].ID != listed[i].ID {
			t.Fatalf("streamed[%d].ID = %q, want listed[%d].ID = %q", i, streamed[i].ID, i, listed[i].ID)
		}
		if streamed[i].Key != listed[i].Key {
			t.Fatalf("streamed[%d].Key = %q, want listed[%d].Key = %q", i, streamed[i].Key, i, listed[i].Key)
		}
	}
}

func TestObjectStoreStreamObjectsInScopePropagatesCallbackError(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	if _, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "stop-me.txt",
	}); err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	callbackErr := fmt.Errorf("callback stopped")
	seen := 0
	err := store.Objects().StreamObjectsInScope(ctx, ObjectScopeParams{BucketID: bucket.ID}, func(object Object) error {
		seen++
		return callbackErr
	})
	if !errors.Is(err, callbackErr) {
		t.Fatalf("StreamObjectsInScope error = %v, want %v", err, callbackErr)
	}
	if seen != 1 {
		t.Fatalf("callback invocations = %d, want 1", seen)
	}
}

func TestObjectStoreStreamObjectsInScopeEmptyScope(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)

	called := false
	err := store.Objects().StreamObjectsInScope(ctx, ObjectScopeParams{BucketID: bucket.ID}, func(object Object) error {
		called = true
		return nil
	})
	if err != nil {
		t.Fatalf("StreamObjectsInScope returned error: %v", err)
	}
	if called {
		t.Fatal("callback was invoked for empty scope")
	}
}

func TestObjectStoreStreamObjectsInScopeRejectsNilCallback(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	err := store.Objects().StreamObjectsInScope(ctx, ObjectScopeParams{}, nil)
	if err == nil {
		t.Fatal("StreamObjectsInScope returned nil error, want callback required error")
	}
}

func TestObjectStoreCountObjectsInScopeMatchesStream(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	scope := ObjectScopeParams{BucketID: bucket.ID, Prefix: "batch/"}

	for _, key := range []string{"batch/a.txt", "batch/b.txt"} {
		if _, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
			BucketID: bucket.ID,
			Key:      key,
		}); err != nil {
			t.Fatalf("UpsertObject %q returned error: %v", key, err)
		}
	}

	count, err := store.Objects().CountObjectsInScope(ctx, scope)
	if err != nil {
		t.Fatalf("CountObjectsInScope returned error: %v", err)
	}

	var streamed int64
	if err := store.Objects().StreamObjectsInScope(ctx, scope, func(object Object) error {
		streamed++
		return nil
	}); err != nil {
		t.Fatalf("StreamObjectsInScope returned error: %v", err)
	}
	if count != streamed {
		t.Fatalf("count = %d, streamed = %d; want equal", count, streamed)
	}
}
