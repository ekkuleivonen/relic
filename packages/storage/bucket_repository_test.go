package storage

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
)

func TestBucketStoreCreateGetList(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	buckets := store.Buckets()
	params := CreateBucketParams{
		Name:        "test-bucket-" + time.Now().Format("20060102150405.000000000"),
		Provider:    BucketProviderS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "example-data",
		Prefix:      "imports/",
		ProviderConfig: BucketProviderConfig{
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
		PluginSettings: BucketPluginSettingsMap{
			"duplicate_detection": {
				Enabled:  false,
				Settings: map[string]any{},
			},
			"background_verification": {
				Enabled: true,
				Settings: map[string]any{
					"interval":    "24h",
					"sample_rate": 0.01,
				},
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
	s3Config, ok := created.ProviderConfig["s3"].(map[string]any)
	if !ok {
		t.Fatalf("created provider config = %#v, want s3 object", created.ProviderConfig)
	}
	if forcePathStyle, ok := s3Config["force_path_style"].(bool); !ok || !forcePathStyle {
		t.Fatalf("force_path_style = %#v, want true", s3Config["force_path_style"])
	}
	if !created.PluginSettings["background_verification"].Enabled {
		t.Fatal("background_verification plugin is not enabled")
	}

	got, err := buckets.GetBucket(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetBucket returned error: %v", err)
	}
	if got.ID != created.ID {
		t.Fatalf("got ID = %q, want %q", got.ID, created.ID)
	}
	if got.PluginSettings["duplicate_detection"].Enabled {
		t.Fatal("duplicate_detection plugin is enabled")
	}

	listed, err := buckets.ListBuckets(ctx, ListBucketsParams{
		Provider: BucketProviderS3,
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

func testStore(t *testing.T, ctx context.Context) (*Store, func()) {
	t.Helper()

	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		t.Skip("DATABASE_URL is not set")
	}

	migrationDir, err := filepath.Abs("migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	if err := RunMigrations(ctx, databaseURL, "file://"+migrationDir); err != nil {
		t.Fatalf("RunMigrations returned error: %v", err)
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
