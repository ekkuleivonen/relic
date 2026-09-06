package runner

import (
	"context"
	"errors"
	"path/filepath"
	"testing"

	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
)

func TestRunnerRetriesFailedJobWhenAttemptsRemain(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()
	clearJobRuns(t, ctx)
	t.Cleanup(func() {
		clearJobRuns(t, context.Background())
	})

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:        storage.JobTypeCleanupRuns,
		MaxAttempts: 2,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	runner := newTestRunner(t, store, failingHandler{jobType: storage.JobTypeCleanupRuns})

	claimed, err := runner.RunOnce(ctx)
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if !claimed {
		t.Fatal("claimed = false, want true")
	}

	retried, err := store.JobRuns().GetJobRun(ctx, run.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if retried.State != storage.JobRunStatePending {
		t.Fatalf("state = %q, want pending", retried.State)
	}
	if retried.Attempt != 2 {
		t.Fatalf("attempt = %d, want 2", retried.Attempt)
	}
	if retried.ErrorMessage != "handler failed" {
		t.Fatalf("error message = %q, want handler failed", retried.ErrorMessage)
	}
}

func TestRunnerFailsJobWhenNoAttemptsRemain(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()
	clearJobRuns(t, ctx)
	t.Cleanup(func() {
		clearJobRuns(t, context.Background())
	})

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type: storage.JobTypeCleanupRuns,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	runner := newTestRunner(t, store, failingHandler{jobType: storage.JobTypeCleanupRuns})

	claimed, err := runner.RunOnce(ctx)
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if !claimed {
		t.Fatal("claimed = false, want true")
	}

	failed, err := store.JobRuns().GetJobRun(ctx, run.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if failed.State != storage.JobRunStateFailed {
		t.Fatalf("state = %q, want failed", failed.State)
	}
	if failed.ErrorMessage != "handler failed" {
		t.Fatalf("error message = %q, want handler failed", failed.ErrorMessage)
	}
}

type failingHandler struct {
	jobType storage.JobType
}

func (h failingHandler) Type() storage.JobType {
	return h.jobType
}

func (h failingHandler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	return nil, errors.New("handler failed")
}

func clearJobRuns(t *testing.T, ctx context.Context) {
	t.Helper()

	pool, err := db.Connect(ctx, testdb.URL(t, ctx))
	if err != nil {
		t.Fatalf("connect for cleanup: %v", err)
	}
	defer pool.Close()

	if _, err := pool.Exec(ctx, "DELETE FROM job_runs"); err != nil {
		t.Fatalf("clear job runs: %v", err)
	}
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
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
