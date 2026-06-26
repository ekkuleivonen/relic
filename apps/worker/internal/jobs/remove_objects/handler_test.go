package remove_objects

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestHandlerDeletesRequestedObjects(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store)
	removeMe, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/remove.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject remove returned error: %v", err)
	}
	keepMe, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/keep.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject keep returned error: %v", err)
	}
	input, err := jobs.PayloadFrom(jobs.ObjectMutationInput{
		BucketID: bucket.ID,
		Objects:  []jobs.ObjectEvidence{{ID: removeMe.ID, Key: removeMe.Key}},
	})
	if err != nil {
		t.Fatalf("PayloadFrom returned error: %v", err)
	}
	run := createJobRun(t, ctx, store, storage.JobTypeRemoveObjects, bucket.ID, input)
	handler, err := NewHandler(HandlerOptions{Store: store})
	if err != nil {
		t.Fatalf("NewHandler returned error: %v", err)
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		t.Fatalf("Handle returned error: %v", err)
	}
	if result["objects_deleted"] != 1 {
		t.Fatalf("objects_deleted = %#v, want 1", result["objects_deleted"])
	}
	if _, err := store.Objects().GetObject(ctx, removeMe.ID); !errors.Is(err, storage.ErrNotFound) {
		t.Fatalf("removed object error = %v, want %v", err, storage.ErrNotFound)
	}
	if _, err := store.Objects().GetObject(ctx, keepMe.ID); err != nil {
		t.Fatalf("kept object returned error: %v", err)
	}
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		t.Skip("DATABASE_URL is not set")
	}

	migrationDir, err := filepath.Abs("../../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	if err := storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir); err != nil {
		t.Fatalf("RunMigrations returned error: %v", err)
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

	return store, pool.Close
}

func createTestBucket(t *testing.T, ctx context.Context, store *storage.Store) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "remove-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "remove-test-data",
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

	return bucket
}

func createJobRun(t *testing.T, ctx context.Context, store *storage.Store, jobType storage.JobType, bucketID string, input storage.JobRunPayload) storage.JobRun {
	t.Helper()

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       jobType,
		TargetType: "bucket",
		TargetID:   bucketID,
		Input:      input,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	return run
}
