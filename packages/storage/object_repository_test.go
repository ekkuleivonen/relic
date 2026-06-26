package storage

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/secrets"
)

func TestObjectStoreUpsertGetList(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()
	seenAt := time.Now().Add(-time.Minute).UTC()

	created, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID:  bucket.ID,
		Key:       "photos/a.jpg",
		VersionID: "v1",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"abc123\"",
				"size":          123456,
				"last_modified": "2026-06-01T00:00:00Z",
				"header": map[string]any{
					"content_type": "image/jpeg",
				},
			},
		},
		AttributeProvenance: ObjectAttributeProvenance{
			"upstream": "jobrun_test",
		},
		SeenAt: &seenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}
	if created.ID == "" {
		t.Fatal("created object ID is empty")
	}
	if created.BucketID != bucket.ID {
		t.Fatalf("created bucket ID = %q, want %q", created.BucketID, bucket.ID)
	}
	if created.AttributeProvenance["upstream"] != "jobrun_test" {
		t.Fatalf("created provenance = %#v, want upstream provenance", created.AttributeProvenance)
	}

	got, err := objects.GetObject(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetObject returned error: %v", err)
	}
	if got.ID != created.ID {
		t.Fatalf("got ID = %q, want %q", got.ID, created.ID)
	}

	listed, err := objects.ListObjects(ctx, ListObjectsParams{
		BucketID:    bucket.ID,
		Prefix:      "photos/",
		ContentType: "image/jpeg",
		KeyContains: "a.j",
		Limit:       50,
	})
	if err != nil {
		t.Fatalf("ListObjects returned error: %v", err)
	}
	if !objectListContains(listed, created.ID) {
		t.Fatalf("ListObjects did not include created object %q", created.ID)
	}

	laterSeenAt := seenAt.Add(time.Minute)
	updated, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID:  bucket.ID,
		Key:       "photos/a.jpg",
		VersionID: "v1",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{
				"etag": "\"def456\"",
				"size": 654321,
				"header": map[string]any{
					"content_type": "image/jpeg",
				},
			},
		},
		AttributeProvenance: ObjectAttributeProvenance{
			"upstream": "jobrun_update",
		},
		SeenAt: &laterSeenAt,
	})
	if err != nil {
		t.Fatalf("second UpsertObject returned error: %v", err)
	}
	if updated.ID != created.ID {
		t.Fatalf("updated ID = %q, want existing ID %q", updated.ID, created.ID)
	}
	if !updated.FirstSeenAt.Equal(created.FirstSeenAt) {
		t.Fatalf("updated first seen = %v, want %v", updated.FirstSeenAt, created.FirstSeenAt)
	}
	if !updated.LastSeenAt.Equal(laterSeenAt) {
		t.Fatalf("updated last seen = %v, want %v", updated.LastSeenAt, laterSeenAt)
	}
	if updated.AttributeProvenance["upstream"] != "jobrun_update" {
		t.Fatalf("updated provenance = %#v, want upstream update provenance", updated.AttributeProvenance)
	}
}

func TestObjectStoreGetMissing(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	_, err := store.Objects().GetObject(ctx, "object_missing")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetObject error = %v, want %v", err, ErrNotFound)
	}
}

func TestObjectStoreDelete(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	created, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "delete-me.txt",
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	if err := store.Objects().DeleteObject(ctx, created.ID); err != nil {
		t.Fatalf("DeleteObject returned error: %v", err)
	}

	_, err = store.Objects().GetObject(ctx, created.ID)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetObject after delete error = %v, want %v", err, ErrNotFound)
	}
}

func TestObjectStoreDeleteObjectsNotSeenSince(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	oldSeenAt := time.Now().Add(-time.Hour).UTC()
	newSeenAt := time.Now().UTC()

	oldObject, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "scope/old.txt",
		SeenAt:   &oldSeenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject old returned error: %v", err)
	}
	newObject, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "scope/new.txt",
		SeenAt:   &newSeenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject new returned error: %v", err)
	}

	deleted, err := store.Objects().DeleteObjectsNotSeenSince(ctx, DeleteObjectsNotSeenSinceParams{
		BucketID: bucket.ID,
		Prefix:   "scope/",
		SeenAt:   newSeenAt,
	})
	if err != nil {
		t.Fatalf("DeleteObjectsNotSeenSince returned error: %v", err)
	}
	if deleted != 1 {
		t.Fatalf("deleted = %d, want 1", deleted)
	}

	_, err = store.Objects().GetObject(ctx, oldObject.ID)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("old object error = %v, want %v", err, ErrNotFound)
	}
	if _, err := store.Objects().GetObject(ctx, newObject.ID); err != nil {
		t.Fatalf("new object should remain, got error: %v", err)
	}
}

func createObjectTestBucket(t *testing.T, ctx context.Context, store *Store) Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:        "object-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "object-test-data",
		EncryptedCredentials: secrets.Envelope{
			KeyID:      "local-dev",
			Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
			Nonce:      []byte("012345678901234567890123"),
			Ciphertext: []byte("encrypted-credentials"),
		},
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", bucket.ID)
	})

	return bucket
}

func objectListContains(objects []Object, id string) bool {
	for _, object := range objects {
		if object.ID == id {
			return true
		}
	}

	return false
}
