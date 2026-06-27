package storage

import (
	"context"
	"errors"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/testdb"
)

var (
	migrateTestStoreOnce sync.Once
	migrateTestStoreErr  error
)

func TestBucketStoreCreateGetList(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	buckets := store.Buckets()
	params := CreateBucketParams{
		Name:        "test-bucket-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "example-data",
		Prefix:      "imports/",
		UpstreamConfig: BucketUpstreamConfig{
			"s3": map[string]any{
				"force_path_style": true,
				"signing_region":   "us-east-1",
			},
		},
		EncryptedCredentials: secrets.Envelope{
			KeyID:      "local-dev",
			Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
			Nonce:      []byte("012345678901234567890123"),
			Ciphertext: []byte("encrypted-credentials"),
		},
		RelicConfig: BucketRelicConfig{
			Scan: BucketScanConfig{
				Enabled:  BoolPtr(true),
				Interval: "24h",
			},
		},
	}

	created, err := buckets.CreateBucket(ctx, params)
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", created.ID)
	})

	if created.ID == "" {
		t.Fatal("created bucket ID is empty")
	}
	if created.Name != params.Name {
		t.Fatalf("created name = %q, want %q", created.Name, params.Name)
	}
	if created.EncryptedCredentials.KeyID != params.EncryptedCredentials.KeyID {
		t.Fatalf("created credential key ID = %q, want %q", created.EncryptedCredentials.KeyID, params.EncryptedCredentials.KeyID)
	}
	s3Config, ok := created.UpstreamConfig["s3"].(map[string]any)
	if !ok {
		t.Fatalf("created upstream config = %#v, want s3 object", created.UpstreamConfig)
	}
	if forcePathStyle, ok := s3Config["force_path_style"].(bool); !ok || !forcePathStyle {
		t.Fatalf("force_path_style = %#v, want true", s3Config["force_path_style"])
	}
	if !created.RelicConfig.ScanEnabled() {
		t.Fatal("scan is not enabled in relic_config")
	}
	if created.RelicConfig.Scan.Interval != "24h" {
		t.Fatalf("scan interval = %q, want 24h", created.RelicConfig.Scan.Interval)
	}

	got, err := buckets.GetBucket(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetBucket returned error: %v", err)
	}
	if got.ID != created.ID {
		t.Fatalf("got ID = %q, want %q", got.ID, created.ID)
	}
	if !got.RelicConfig.ScanEnabled() {
		t.Fatal("scan is not enabled in relic_config")
	}

	listed, err := buckets.ListBuckets(ctx, ListBucketsParams{
		Upstream: BucketUpstreamS3,
		Limit:    50,
	})
	if err != nil {
		t.Fatalf("ListBuckets returned error: %v", err)
	}
	if !bucketListContains(listed, created.ID) {
		t.Fatalf("ListBuckets did not include created bucket %q", created.ID)
	}
}

func TestBucketStoreGetMissing(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	_, err := store.Buckets().GetBucket(ctx, "bucket_missing")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetBucket error = %v, want %v", err, ErrNotFound)
	}
}

func TestBucketStoreUpdate(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	buckets := store.Buckets()
	created, err := buckets.CreateBucket(ctx, CreateBucketParams{
		Name:        "update-source-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://wrong.example.test",
		Region:      "us-east-1",
		BucketName:  "example-data",
		Prefix:      "old/",
		UpstreamConfig: BucketUpstreamConfig{
			"s3": map[string]any{
				"force_path_style": false,
			},
		},
		EncryptedCredentials: secrets.Envelope{
			KeyID:      "local-dev",
			Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
			Nonce:      []byte("012345678901234567890123"),
			Ciphertext: []byte("encrypted-credentials"),
		},
		RelicConfig: BucketRelicConfig{},
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", created.ID)
	})

	name := "updated-bucket-" + time.Now().Format("20060102150405.000000000")
	endpointURL := "https://s3.correct.example.test"
	region := "eu-west-1"
	prefix := "new/"
	upstreamConfig := BucketUpstreamConfig{
		"s3": map[string]any{
			"force_path_style": true,
			"signing_region":   region,
		},
	}

	updated, err := buckets.UpdateBucket(ctx, UpdateBucketParams{
		ID:             created.ID,
		Name:           &name,
		EndpointURL:    &endpointURL,
		Region:         &region,
		Prefix:         &prefix,
		UpstreamConfig: &upstreamConfig,
	})
	if err != nil {
		t.Fatalf("UpdateBucket returned error: %v", err)
	}

	if updated.Name != name {
		t.Fatalf("updated name = %q, want %q", updated.Name, name)
	}
	if updated.EndpointURL != endpointURL {
		t.Fatalf("updated endpoint URL = %q, want %q", updated.EndpointURL, endpointURL)
	}
	if updated.Region != region {
		t.Fatalf("updated region = %q, want %q", updated.Region, region)
	}
	if updated.Prefix != prefix {
		t.Fatalf("updated prefix = %q, want %q", updated.Prefix, prefix)
	}
	if updated.BucketName != created.BucketName {
		t.Fatalf("updated bucket name = %q, want %q", updated.BucketName, created.BucketName)
	}
	s3Config, ok := updated.UpstreamConfig["s3"].(map[string]any)
	if !ok {
		t.Fatalf("updated upstream config = %#v, want s3 object", updated.UpstreamConfig)
	}
	if forcePathStyle, ok := s3Config["force_path_style"].(bool); !ok || !forcePathStyle {
		t.Fatalf("force_path_style = %#v, want true", s3Config["force_path_style"])
	}
}

func TestBucketStoreDeleteCascadesObjects(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:        "delete-source-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "example-data",
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
	object, err := store.Objects().UpsertObject(ctx, UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	if err := store.Buckets().DeleteBucket(ctx, bucket.ID); err != nil {
		t.Fatalf("DeleteBucket returned error: %v", err)
	}
	if _, err := store.Buckets().GetBucket(ctx, bucket.ID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetBucket after delete error = %v, want %v", err, ErrNotFound)
	}
	if _, err := store.Objects().GetObject(ctx, object.ID); !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetObject after bucket delete error = %v, want %v", err, ErrNotFound)
	}
}

func TestBucketStoreDeleteMissing(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	err := store.Buckets().DeleteBucket(ctx, "bucket_missing")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("DeleteBucket error = %v, want %v", err, ErrNotFound)
	}
}

func testStore(t *testing.T, ctx context.Context) (*Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateTestStoreOnce.Do(func() {
		migrateTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
			return RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateTestStoreErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateTestStoreErr))
	}

	pool, err := db.Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Connect returned error: %v", err)
	}

	store, err := New(pool)
	if err != nil {
		pool.Close()
		t.Fatalf("New returned error: %v", err)
	}
	if err := PrepareTestStore(ctx, store); err != nil {
		pool.Close()
		t.Fatalf("PrepareTestStore returned error: %v", err)
	}

	return store, pool.Close
}

func bucketListContains(buckets []Bucket, id string) bool {
	for _, bucket := range buckets {
		if bucket.ID == id {
			return true
		}
	}

	return false
}
