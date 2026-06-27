package upstreamprocessor

import (
	"context"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/testdb"
)

var (
	migrateProcessorTestStoreOnce sync.Once
	migrateProcessorTestStoreErr  error
)

func TestProcessorTickEnqueuesImportObjects(t *testing.T) {
	ctx := context.Background()
	store, cleanup := processorTestStore(t, ctx)
	defer cleanup()

	bucket := createProcessorTestBucket(t, ctx, store, "raw/", "processor-import-data")
	if _, err := store.UpstreamEvents().CreateUpstreamEvent(ctx, storage.CreateUpstreamEventParams{
		BucketID:           &bucket.ID,
		UpstreamBucketName: bucket.BucketName,
		EventName:          "ObjectCreated:Put",
		ObjectKey:          "raw/photos/a.jpg",
		Envelope:           storage.JobRunPayload{"event": "ObjectCreated:Put"},
		DedupeKey:          uniqueDedupeKey("import"),
		Transport:          storage.UpstreamEventTransportWebhook,
	}); err != nil {
		t.Fatalf("CreateUpstreamEvent returned error: %v", err)
	}

	processor, err := NewProcessor(ProcessorOptions{Store: store, BatchSize: 10})
	if err != nil {
		t.Fatalf("NewProcessor returned error: %v", err)
	}

	processed, err := processor.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed = %d, want 1", processed)
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:            storage.JobTypeImportObjects,
		TargetType:      "bucket",
		TargetID:        bucket.ID,
		RequestedByType: "upstream_event",
		Limit:           10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("import job count = %d, want 1", len(runs))
	}
}

func TestProcessorTickCoalescesDuplicateImports(t *testing.T) {
	ctx := context.Background()
	store, cleanup := processorTestStore(t, ctx)
	defer cleanup()

	bucket := createProcessorTestBucket(t, ctx, store, "", "processor-coalesce-data")
	for i, dedupe := range []string{uniqueDedupeKey("coalesce-1"), uniqueDedupeKey("coalesce-2")} {
		if _, err := store.UpstreamEvents().CreateUpstreamEvent(ctx, storage.CreateUpstreamEventParams{
			BucketID:           &bucket.ID,
			UpstreamBucketName: bucket.BucketName,
			EventName:          "ObjectCreated:Put",
			ObjectKey:          "photos/a.jpg",
			Envelope:           storage.JobRunPayload{"seq": i},
			DedupeKey:          dedupe,
			Transport:          storage.UpstreamEventTransportWebhook,
		}); err != nil {
			t.Fatalf("CreateUpstreamEvent returned error: %v", err)
		}
	}

	processor, err := NewProcessor(ProcessorOptions{Store: store, BatchSize: 10})
	if err != nil {
		t.Fatalf("NewProcessor returned error: %v", err)
	}

	processed, err := processor.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if processed != 2 {
		t.Fatalf("processed = %d, want 2", processed)
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:       storage.JobTypeImportObjects,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("import job count = %d, want 1", len(runs))
	}
}

func TestProcessorTickResolvesBucketByUpstreamName(t *testing.T) {
	ctx := context.Background()
	store, cleanup := processorTestStore(t, ctx)
	defer cleanup()

	bucket := createProcessorTestBucket(t, ctx, store, "", "processor-resolve-data")
	if _, err := store.UpstreamEvents().CreateUpstreamEvent(ctx, storage.CreateUpstreamEventParams{
		UpstreamBucketName: bucket.BucketName,
		EventName:          "ObjectCreated:Put",
		ObjectKey:          "photos/a.jpg",
		Envelope:           storage.JobRunPayload{"event": "ObjectCreated:Put"},
		DedupeKey:          uniqueDedupeKey("resolve"),
		Transport:          storage.UpstreamEventTransportWebhook,
	}); err != nil {
		t.Fatalf("CreateUpstreamEvent returned error: %v", err)
	}

	processor, err := NewProcessor(ProcessorOptions{Store: store, BatchSize: 10})
	if err != nil {
		t.Fatalf("NewProcessor returned error: %v", err)
	}

	if _, err := processor.Tick(ctx); err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:       storage.JobTypeImportObjects,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("import job count = %d, want 1", len(runs))
	}
}

func TestProcessorTickEnqueuesRemoveObjectsWithResolvedID(t *testing.T) {
	ctx := context.Background()
	store, cleanup := processorTestStore(t, ctx)
	defer cleanup()

	bucket := createProcessorTestBucket(t, ctx, store, "", "processor-remove-data")
	object, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "photos/a.jpg",
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	if _, err := store.UpstreamEvents().CreateUpstreamEvent(ctx, storage.CreateUpstreamEventParams{
		BucketID:           &bucket.ID,
		UpstreamBucketName: bucket.BucketName,
		EventName:          "ObjectRemoved:Delete",
		ObjectKey:          object.Key,
		Envelope:           storage.JobRunPayload{"event": "ObjectRemoved:Delete"},
		DedupeKey:          uniqueDedupeKey("remove"),
		Transport:          storage.UpstreamEventTransportWebhook,
	}); err != nil {
		t.Fatalf("CreateUpstreamEvent returned error: %v", err)
	}

	processor, err := NewProcessor(ProcessorOptions{Store: store, BatchSize: 10})
	if err != nil {
		t.Fatalf("NewProcessor returned error: %v", err)
	}

	if _, err := processor.Tick(ctx); err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:       storage.JobTypeRemoveObjects,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("remove job count = %d, want 1", len(runs))
	}
}

func TestProcessorTickSkipsOutOfScopeKey(t *testing.T) {
	ctx := context.Background()
	store, cleanup := processorTestStore(t, ctx)
	defer cleanup()

	bucket := createProcessorTestBucket(t, ctx, store, "raw/", "processor-scope-data")
	event, err := store.UpstreamEvents().CreateUpstreamEvent(ctx, storage.CreateUpstreamEventParams{
		BucketID:           &bucket.ID,
		UpstreamBucketName: bucket.BucketName,
		EventName:          "ObjectCreated:Put",
		ObjectKey:          "other/a.jpg",
		Envelope:           storage.JobRunPayload{"event": "ObjectCreated:Put"},
		DedupeKey:          uniqueDedupeKey("scope"),
		Transport:          storage.UpstreamEventTransportWebhook,
	})
	if err != nil {
		t.Fatalf("CreateUpstreamEvent returned error: %v", err)
	}

	processor, err := NewProcessor(ProcessorOptions{Store: store, BatchSize: 10})
	if err != nil {
		t.Fatalf("NewProcessor returned error: %v", err)
	}

	if _, err := processor.Tick(ctx); err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}

	got, err := store.UpstreamEvents().GetUpstreamEvent(ctx, event.ID)
	if err != nil {
		t.Fatalf("GetUpstreamEvent returned error: %v", err)
	}
	if got.State != storage.UpstreamEventStateSkipped {
		t.Fatalf("state = %q, want skipped", got.State)
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:       storage.JobTypeImportObjects,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 0 {
		t.Fatalf("import job count = %d, want 0", len(runs))
	}
}

func processorTestStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateProcessorTestStoreOnce.Do(func() {
		migrateProcessorTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
			return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateProcessorTestStoreErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateProcessorTestStoreErr))
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

func TestProcessorTickResolvesBucketByAWSOrigin(t *testing.T) {
	ctx := context.Background()
	store, cleanup := processorTestStore(t, ctx)
	defer cleanup()

	bucket := createProcessorTestBucketWithEndpoint(t, ctx, store, "", "shared-origin-data", "https://s3.amazonaws.com", "us-west-2")
	other := createProcessorTestBucketWithEndpoint(t, ctx, store, "", "shared-origin-data", "https://s3.amazonaws.com", "us-east-1")
	_ = other

	if _, err := store.UpstreamEvents().CreateUpstreamEvent(ctx, storage.CreateUpstreamEventParams{
		UpstreamBucketName: bucket.BucketName,
		UpstreamPlatform:   "aws",
		UpstreamRegion:     "us-west-2",
		UpstreamOrigin:     "aws:us-west-2",
		EventName:          "ObjectCreated:Put",
		ObjectKey:          "photos/a.jpg",
		Envelope:           storage.JobRunPayload{"event": "ObjectCreated:Put"},
		DedupeKey:          uniqueDedupeKey("origin"),
		Transport:          storage.UpstreamEventTransportWebhook,
	}); err != nil {
		t.Fatalf("CreateUpstreamEvent returned error: %v", err)
	}

	processor, err := NewProcessor(ProcessorOptions{Store: store, BatchSize: 10})
	if err != nil {
		t.Fatalf("NewProcessor returned error: %v", err)
	}

	if _, err := processor.Tick(ctx); err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:       storage.JobTypeImportObjects,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("import job count = %d, want 1", len(runs))
	}
}

func createProcessorTestBucketWithEndpoint(
	t *testing.T,
	ctx context.Context,
	store *storage.Store,
	prefix string,
	bucketName string,
	endpointURL string,
	region string,
) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "processor-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: endpointURL,
		Region:      region,
		BucketName:  bucketName,
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
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	return bucket
}

func createProcessorTestBucket(
	t *testing.T,
	ctx context.Context,
	store *storage.Store,
	prefix string,
	bucketName string,
) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "processor-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  bucketName,
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
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	return bucket
}

func uniqueDedupeKey(prefix string) string {
	return prefix + "-" + time.Now().Format("20060102150405.000000000")
}
