package storage

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/secrets"
)

func TestObjectStoreUpsertGetList(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()
	seenAt := time.Now().Add(-time.Minute).UTC()

	created, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
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
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
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

func TestObjectStoreUpsertObjectsInsertUpdateAndEmpty(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()
	seenAt := time.Now().Add(-time.Minute).UTC()

	empty, err := objects.UpsertObjects(ctx, nil)
	if err != nil {
		t.Fatalf("UpsertObjects empty returned error: %v", err)
	}
	if len(empty) != 0 {
		t.Fatalf("empty result length = %d, want 0", len(empty))
	}

	created, err := objects.UpsertObjects(ctx, []UpsertObjectParams{
		{
			BucketID: bucket.ID,
			Key:      "batch/a.jpg",
			Attributes: ObjectAttributes{
				"upstream": map[string]any{"etag": "\"a\""},
			},
			AttributeProvenance: ObjectAttributeProvenance{"upstream": "jobrun_import"},
			SeenAt:              &seenAt,
		},
		{
			BucketID: bucket.ID,
			Key:      "batch/b.jpg",
			Attributes: ObjectAttributes{
				"upstream": map[string]any{"etag": "\"b\""},
			},
			AttributeProvenance: ObjectAttributeProvenance{"upstream": "jobrun_import"},
			SeenAt:              &seenAt,
		},
	})
	if err != nil {
		t.Fatalf("UpsertObjects insert returned error: %v", err)
	}
	if len(created) != 2 {
		t.Fatalf("created length = %d, want 2", len(created))
	}
	if created[0].Key != "batch/a.jpg" || created[1].Key != "batch/b.jpg" {
		t.Fatalf("created order = %q, %q; want batch order", created[0].Key, created[1].Key)
	}

	laterSeenAt := seenAt.Add(time.Minute)
	updated, err := objects.UpsertObjects(ctx, []UpsertObjectParams{
		{
			BucketID: bucket.ID,
			Key:      "batch/a.jpg",
			Attributes: ObjectAttributes{
				"upstream": map[string]any{"etag": "\"updated\""},
			},
			AttributeProvenance: ObjectAttributeProvenance{"upstream": "jobrun_refresh"},
			SeenAt:              &laterSeenAt,
		},
	})
	if err != nil {
		t.Fatalf("UpsertObjects update returned error: %v", err)
	}
	if len(updated) != 1 {
		t.Fatalf("updated length = %d, want 1", len(updated))
	}
	if updated[0].ID != created[0].ID {
		t.Fatalf("updated ID = %q, want existing ID %q", updated[0].ID, created[0].ID)
	}
	if !updated[0].FirstSeenAt.Equal(created[0].FirstSeenAt) {
		t.Fatalf("updated first seen = %v, want %v", updated[0].FirstSeenAt, created[0].FirstSeenAt)
	}
	if !updated[0].LastSeenAt.Equal(laterSeenAt) {
		t.Fatalf("updated last seen = %v, want %v", updated[0].LastSeenAt, laterSeenAt)
	}
	if updated[0].AttributeProvenance["upstream"] != "jobrun_refresh" {
		t.Fatalf("updated provenance = %#v, want refresh provenance", updated[0].AttributeProvenance)
	}
}

func TestObjectStoreUpsertPreservesUserAttributes(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	objects := store.Objects()
	seenAt := time.Now().UTC()

	created, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "preserve/user.jpg",
		Attributes: ObjectAttributes{
			"user": map[string]any{
				"owner": "finance",
			},
		},
		AttributeProvenance: ObjectAttributeProvenance{
			"user.owner": "user_admin",
		},
		SeenAt: &seenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	laterSeenAt := seenAt.Add(time.Minute)
	synced, err := objects.UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "preserve/user.jpg",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{
				"etag": "\"synced\"",
				"size": 2048,
			},
		},
		AttributeProvenance: ObjectAttributeProvenance{
			"upstream": "jobrun_sync",
		},
		SeenAt: &laterSeenAt,
	})
	if err != nil {
		t.Fatalf("second UpsertObject returned error: %v", err)
	}
	if synced.ID != created.ID {
		t.Fatalf("synced ID = %q, want %q", synced.ID, created.ID)
	}

	owner, ok := attributeValue(synced.Attributes, "user.owner")
	if !ok || owner != "finance" {
		t.Fatalf("user.owner = %#v, want finance", owner)
	}
	etag, ok := attributeValue(synced.Attributes, "upstream.etag")
	if !ok || etag != "\"synced\"" {
		t.Fatalf("upstream.etag = %#v, want synced etag", etag)
	}
	if synced.AttributeProvenance["user.owner"] != "user_admin" {
		t.Fatalf("user.owner provenance = %q, want user_admin", synced.AttributeProvenance["user.owner"])
	}
	if synced.AttributeProvenance["upstream"] != "jobrun_sync" {
		t.Fatalf("upstream provenance = %q, want jobrun_sync", synced.AttributeProvenance["upstream"])
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

func TestObjectStoreListObjectsInScopeAndDeleteObjects(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createObjectTestBucket(t, ctx, store)
	photosObject, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject photos returned error: %v", err)
	}
	_, err = store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "docs/readme.md",
	})
	if err != nil {
		t.Fatalf("UpsertObject docs returned error: %v", err)
	}

	scoped, err := store.Objects().ListObjectsInScope(ctx, ObjectScopeParams{
		BucketID: bucket.ID,
		Prefix:   "photos/",
	})
	if err != nil {
		t.Fatalf("ListObjectsInScope returned error: %v", err)
	}
	if len(scoped) != 1 || scoped[0].ID != photosObject.ID {
		t.Fatalf("scoped objects = %#v, want only %q", scoped, photosObject.ID)
	}

	deleted, err := store.Objects().DeleteObjects(ctx, DeleteObjectsParams{
		IDs: []string{photosObject.ID},
	})
	if err != nil {
		t.Fatalf("DeleteObjects returned error: %v", err)
	}
	if deleted != 1 {
		t.Fatalf("deleted = %d, want 1", deleted)
	}
}

func TestObjectStoreDeleteObjectsEmpty(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	deleted, err := store.Objects().DeleteObjects(ctx, DeleteObjectsParams{})
	if err != nil {
		t.Fatalf("DeleteObjects returned error: %v", err)
	}
	if deleted != 0 {
		t.Fatalf("deleted = %d, want 0", deleted)
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

func TestObjectStoreSearchPithosysQLRelativeTime(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	bucket := createObjectTestBucket(t, ctx, store)
	recentSeenAt := time.Now().Add(-24 * time.Hour).UTC()
	oldSeenAt := time.Now().Add(-10 * 24 * time.Hour).UTC()

	recentObject, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "scope/recent.txt",
		SeenAt:   &recentSeenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject recent returned error: %v", err)
	}
	_, err = store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "scope/old.txt",
		SeenAt:   &oldSeenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject old returned error: %v", err)
	}

	results, err := store.SearchPithosysQL(ctx, `
		FROM objects
		WHERE attr('core.last_seen_at') >= now() - interval '7 days'
	`, SearchScope{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("SearchPithosysQL returned error: %v", err)
	}
	if len(results) != 1 {
		t.Fatalf("results length = %d, want 1; got %#v", len(results), results)
	}
	if results[0].ID != recentObject.ID {
		t.Fatalf("result ID = %q, want %q", results[0].ID, recentObject.ID)
	}
}

func TestObjectStoreSearchPithosysQL(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	bucket := createObjectTestBucket(t, ctx, store)
	otherBucket := createObjectTestBucket(t, ctx, store)

	photo, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{
				"size": 2048,
				"header": map[string]any{
					"content_type": "image/jpeg",
				},
			},
			"user": map[string]any{
				"score": 150,
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject photo returned error: %v", err)
	}
	_, err = store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "docs/readme.md",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{
				"size": 512,
				"header": map[string]any{
					"content_type": "text/markdown",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject doc returned error: %v", err)
	}
	_, err = store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: otherBucket.ID,
		Key:      "photos/a.jpg",
		Attributes: ObjectAttributes{
			"upstream": map[string]any{
				"size": 4096,
				"header": map[string]any{
					"content_type": "image/jpeg",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject other bucket returned error: %v", err)
	}

	results, err := store.SearchPithosysQL(ctx, `
		FROM objects
		WHERE attr('user.score')::integer >= 100
		  AND attr('upstream.header.content_type') = 'image/jpeg'
		ORDER BY key ASC
	`, SearchScope{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("SearchPithosysQL returned error: %v", err)
	}
	if len(results) != 1 {
		t.Fatalf("results length = %d, want 1; got %#v", len(results), results)
	}
	if results[0].ID != photo.ID {
		t.Fatalf("result ID = %q, want %q", results[0].ID, photo.ID)
	}
}

func TestObjectStoreSearchPithosysQL_HasRelation(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		t.Fatalf("SeedAttributeCatalog returned error: %v", err)
	}

	bucket := createObjectTestBucket(t, ctx, store)
	source, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "source.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject source returned error: %v", err)
	}
	target, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "target.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject target returned error: %v", err)
	}
	_, err = store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "unrelated.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject unrelated returned error: %v", err)
	}

	_, err = store.pool.Exec(ctx, `
		INSERT INTO relations (
			id,
			source_object_id,
			target_object_id,
			relation_type
		) VALUES ($1, $2, $3, $4)
	`, "relation_test_duplicate", source.ID, target.ID, "duplicate")
	if err != nil {
		t.Fatalf("insert relation returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM relations WHERE id = $1", "relation_test_duplicate")
	})

	results, err := store.SearchPithosysQL(ctx, `
		FROM objects
		WHERE has_relation('duplicate', 'out')
	`, SearchScope{BucketID: bucket.ID})
	if err != nil {
		t.Fatalf("SearchPithosysQL returned error: %v", err)
	}
	if len(results) != 1 {
		t.Fatalf("results length = %d, want 1; got %#v", len(results), results)
	}
	if results[0].ID != source.ID {
		t.Fatalf("result ID = %q, want %q", results[0].ID, source.ID)
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
