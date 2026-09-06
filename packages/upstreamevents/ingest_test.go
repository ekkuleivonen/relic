package upstreamevents

import (
	"context"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
)

var (
	migrateIngestTestStoreOnce sync.Once
	migrateIngestTestStoreErr  error
)

func TestIngestS3NotificationJetstreamTransport(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "ingest-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://rustfs.example.test:9000",
		Region:      "us-east-1",
		BucketName:  "pithosys-test-01",
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
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	body := loadFixture(t, "rustfs_object_created.json")
	result, err := IngestS3Notification(
		ctx,
		store.UpstreamEvents(),
		body,
		bucket.ID,
	)
	if err != nil {
		t.Fatalf("IngestS3Notification returned error: %v", err)
	}
	if result.Accepted != 1 {
		t.Fatalf("accepted = %d, want 1", result.Accepted)
	}

	event, err := store.UpstreamEvents().GetUpstreamEvent(ctx, result.EventIDs[0])
	if err != nil {
		t.Fatalf("GetUpstreamEvent returned error: %v", err)
	}
	if event.Transport != storage.UpstreamEventTransportJetstream {
		t.Fatalf("transport = %q, want jetstream", event.Transport)
	}
	if event.BucketID != bucket.ID {
		t.Fatalf("bucket_id = %q, want %q", event.BucketID, bucket.ID)
	}
	if event.ObjectKey != "photos/a.jpg" {
		t.Fatalf("object key = %q, want photos/a.jpg", event.ObjectKey)
	}
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	database, err := db.Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("connect test database: %v", err)
	}

	migrateIngestTestStoreOnce.Do(func() {
		migrateIngestTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "upstream_events", func() error {
			return storage.RunMigrations(ctx, databaseURL, "")
		})
	})
	if migrateIngestTestStoreErr != nil {
		database.Close()
		t.Fatal(testdb.MigrationTimeoutError(migrateIngestTestStoreErr))
	}

	store, err := storage.New(database)
	if err != nil {
		database.Close()
		t.Fatalf("create storage store: %v", err)
	}

	return store, func() {
		database.Close()
	}
}

func loadFixture(t *testing.T, name string) []byte {
	t.Helper()

	path := filepath.Join("..", "upstreams", "s3events", "testdata", "notifications", name)
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %s: %v", name, err)
	}

	return body
}
