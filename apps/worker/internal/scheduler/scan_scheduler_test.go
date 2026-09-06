package scheduler

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/settings"
	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
)

func TestScanSchedulerTickEnqueuesDueScan(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	bucket := createSchedulerTestBucket(t, ctx, store, storage.BucketPithosysConfig{
		Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true), Interval: "24h"},
	})

	scheduler, err := NewScanScheduler(ScanSchedulerOptions{
		Store:    store,
		Now:      func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: schedulerTestSettings(),
	})
	if err != nil {
		t.Fatalf("NewScanScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued != 1 {
		t.Fatalf("enqueued = %d, want 1", enqueued)
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:       storage.JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("scan job count = %d, want 1", len(runs))
	}
	if runs[0].RequestedByType != "scheduler" {
		t.Fatalf("requested_by_type = %q, want scheduler", runs[0].RequestedByType)
	}
}

func TestScanSchedulerTickDedupesActiveScan(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	bucket := createSchedulerTestBucket(t, ctx, store, storage.BucketPithosysConfig{
		Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true)},
	})
	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	}); err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	scheduler, err := NewScanScheduler(ScanSchedulerOptions{
		Store:    store,
		Now:      func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: schedulerTestSettings(),
	})
	if err != nil {
		t.Fatalf("NewScanScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued != 0 {
		t.Fatalf("enqueued = %d, want 0", enqueued)
	}
}

func TestScanSchedulerTickSkipsWhenSyncTraceActive(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	bucket := createSchedulerTestBucket(t, ctx, store, storage.BucketPithosysConfig{
		Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true), Interval: "24h"},
	})
	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
			"objects":   []any{},
		},
	}); err != nil {
		t.Fatalf("CreateJobRun child returned error: %v", err)
	}

	scheduler, err := NewScanScheduler(ScanSchedulerOptions{
		Store:    store,
		Now:      func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: schedulerTestSettings(),
	})
	if err != nil {
		t.Fatalf("NewScanScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued != 0 {
		t.Fatalf("enqueued = %d, want 0 while sync trace active", enqueued)
	}
}

func TestScanSchedulerTickSkipsWhenScanTraceSyncChildActive(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	bucket := createSchedulerTestBucket(t, ctx, store, storage.BucketPithosysConfig{
		Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true), Interval: "24h"},
	})
	scanRoot, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun scan root returned error: %v", err)
	}
	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeSyncBucket,
		RequestedByType: "job",
		RequestedByID:   scanRoot.ID,
		TargetType:      "bucket",
		TargetID:        bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	}); err != nil {
		t.Fatalf("CreateJobRun sync child returned error: %v", err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{ID: scanRoot.ID}); err != nil {
		t.Fatalf("SucceedJobRun scan root returned error: %v", err)
	}

	scheduler, err := NewScanScheduler(ScanSchedulerOptions{
		Store:    store,
		Now:      func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: schedulerTestSettings(),
	})
	if err != nil {
		t.Fatalf("NewScanScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued != 0 {
		t.Fatalf("enqueued = %d, want 0 while scan-escalated sync child is active", enqueued)
	}
}

func TestScanSchedulerTickSkipsWhenNotDue(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	bucket := createSchedulerTestBucket(t, ctx, store, storage.BucketPithosysConfig{
		Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true), Interval: "24h"},
	})
	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{
		ID:     run.ID,
		Result: storage.JobRunPayload{"status": "healthy"},
	}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	scheduler, err := NewScanScheduler(ScanSchedulerOptions{
		Store:    store,
		Now:      func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: schedulerTestSettings(),
	})
	if err != nil {
		t.Fatalf("NewScanScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued != 0 {
		t.Fatalf("enqueued = %d, want 0", enqueued)
	}
}

func TestScanSchedulerTickSkipsWhenRecentFailedScan(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	bucket := createSchedulerTestBucket(t, ctx, store, storage.BucketPithosysConfig{
		Scan: storage.BucketScanConfig{Enabled: storage.BoolPtr(true), Interval: "24h"},
	})
	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().FailJobRun(ctx, storage.FailJobRunParams{
		ID:           run.ID,
		ErrorMessage: "upstream list timeout",
	}); err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}

	scheduler, err := NewScanScheduler(ScanSchedulerOptions{
		Store: store,
		Now: func() time.Time {
			return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)
		},
		Settings: schedulerTestSettings(),
	})
	if err != nil {
		t.Fatalf("NewScanScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued != 0 {
		t.Fatalf("enqueued = %d, want 0 after recent failed scan", enqueued)
	}
}

func schedulerTestStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	if err := testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
		return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
	}); err != nil {
		t.Fatal(testdb.MigrationTimeoutError(err))
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

func createSchedulerTestBucket(t *testing.T, ctx context.Context, store *storage.Store, pithosysConfig storage.BucketPithosysConfig) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "scheduler-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "scheduler-test-data",
		EncryptedCredentials: secrets.Envelope{
			KeyID:      "local-dev",
			Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
			Nonce:      []byte("012345678901234567890123"),
			Ciphertext: []byte("encrypted-credentials"),
		},
		PithosysConfig: pithosysConfig,
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{})
		_, _ = store.Objects().DeleteObjectsNotSeenSince(context.Background(), storage.DeleteObjectsNotSeenSinceParams{
			BucketID: bucket.ID,
			SeenAt:   time.Now().Add(time.Hour),
		})
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	return bucket
}

func schedulerTestSettings() settings.Static {
	values := settings.StaticFromRegistry()
	values[storage.SettingWorkerScanStagger] = "0s"
	return settings.Static(values)
}
