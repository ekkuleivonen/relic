package sync_bucket

import (
	"context"
	"fmt"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
	"github.com/elei-io/pithosys/packages/verification"
)

var (
	migrateScopeTestStoreOnce sync.Once
	migrateScopeTestStoreErr  error
)

func TestCollectLocalObjectsInScopeWithoutPartitionReturnsAll(t *testing.T) {
	ctx := context.Background()
	store, cleanup := scopeTestStore(t, ctx)
	defer cleanup()

	bucket := createScopeTestBucket(t, ctx, store, "")
	upsertScopeObject(t, ctx, store, bucket.ID, "a.txt")
	upsertScopeObject(t, ctx, store, bucket.ID, "b.txt")

	objects, err := collectLocalObjectsInScope(ctx, store.Objects(), ObjectScopeParams(bucket.ID, "", SyncBucketInput{}), nil)
	if err != nil {
		t.Fatalf("collectLocalObjectsInScope returned error: %v", err)
	}
	if len(objects) != 2 {
		t.Fatalf("len(objects) = %d, want 2", len(objects))
	}
}

func TestCollectLocalObjectsInScopeWithPartitionFiltersDuringStream(t *testing.T) {
	ctx := context.Background()
	store, cleanup := scopeTestStore(t, ctx)
	defer cleanup()

	bucket := createScopeTestBucket(t, ctx, store, "")
	partition := verification.PartitionFromIndex(42, verification.DefaultModulus)
	keyIn := keyForScopePartitionIndex(t, partition.Index, partition.Modulus)
	keyOut := keyForScopePartitionIndex(t, 99, partition.Modulus)

	upsertScopeObject(t, ctx, store, bucket.ID, keyIn)
	upsertScopeObject(t, ctx, store, bucket.ID, keyOut)

	objects, err := collectLocalObjectsInScope(ctx, store.Objects(), ObjectScopeParams(bucket.ID, "", SyncBucketInput{}), &partition)
	if err != nil {
		t.Fatalf("collectLocalObjectsInScope returned error: %v", err)
	}
	if len(objects) != 1 {
		t.Fatalf("len(objects) = %d, want 1", len(objects))
	}
	if objects[0].Key != keyIn {
		t.Fatalf("object key = %q, want %q", objects[0].Key, keyIn)
	}
}

func scopeTestStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateScopeTestStoreOnce.Do(func() {
		migrateScopeTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
			return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateScopeTestStoreErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateScopeTestStoreErr))
	}

	pool, err := db.Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Connect returned error: %v", err)
	}

	store, err := storage.New(pool)
	if err != nil {
		pool.Close()
		t.Fatalf("New returned error: %v", err)
	}
	if err := storage.PrepareTestStore(ctx, store); err != nil {
		pool.Close()
		t.Fatalf("PrepareTestStore returned error: %v", err)
	}

	return store, pool.Close
}

func createScopeTestBucket(t *testing.T, ctx context.Context, store *storage.Store, prefix string) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "scope-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "scope-test-data",
		Prefix:      prefix,
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
		_, _ = store.Objects().DeleteObjectsNotSeenSince(context.Background(), storage.DeleteObjectsNotSeenSinceParams{
			BucketID: bucket.ID,
			SeenAt:   time.Now().Add(time.Hour),
		})
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	return bucket
}

func upsertScopeObject(t *testing.T, ctx context.Context, store *storage.Store, bucketID, key string) {
	t.Helper()

	_, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucketID,
		Key:      key,
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          fmt.Sprintf("\"%s\"", key),
				"size":          int64(100),
				"last_modified": time.Date(2026, 6, 27, 12, 0, 0, 0, time.UTC).Format(time.RFC3339),
				"s3": map[string]any{
					"storage_class": "STANDARD",
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}
}

func keyForScopePartitionIndex(t *testing.T, index, modulus uint32) string {
	t.Helper()

	for i := range 10_000 {
		key := fmt.Sprintf("objects/%d.dat", i)
		if verification.PartitionIndex(key, modulus) == index {
			return key
		}
	}

	t.Fatalf("could not find key for partition %d/%d", index, modulus)
	return ""
}
