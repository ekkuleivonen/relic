package tracecompletion

import (
	"context"
	"io"
	"log/slog"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/testdb"
)

var (
	migrateTestStoreOnce sync.Once
	migrateTestStoreErr  error
)

func TestTickerFinalizesAwaitingJobWithManyChildren(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type: storage.JobTypeSyncBucket,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	if _, err := store.JobRuns().ClaimJobRun(ctx, storage.ClaimJobRunParams{WorkerID: "test-worker"}); err != nil {
		t.Fatalf("ClaimJobRun returned error: %v", err)
	}

	result := storage.JobRunPayload{
		"await_children":       true,
		"objects_seen":         int64(600),
		"import_objects_count": 600,
		"child_job_ids": map[string]any{
			"import_objects": []any{},
		},
	}
	if _, err := store.JobRuns().AwaitJobRunChildren(ctx, storage.AwaitJobRunChildrenParams{
		ID:     root.ID,
		Result: result,
		Progress: storage.JobRunPayload{
			"phase":                "importing",
			"objects_listed":       int64(600),
			"import_objects_count": 600,
		},
	}); err != nil {
		t.Fatalf("AwaitJobRunChildren returned error: %v", err)
	}

	const childCount = 600
	for range childCount {
		if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
			Type:            storage.JobTypeImportObjects,
			RequestedByType: "job",
			RequestedByID:   root.ID,
		}); err != nil {
			t.Fatalf("CreateJobRun returned error: %v", err)
		}
	}

	children, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		RequestedByType: "job",
		RequestedByID:   root.ID,
		Limit:           500,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	for _, child := range children {
		if _, err := store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{ID: child.ID}); err != nil {
			t.Fatalf("SucceedJobRun returned error: %v", err)
		}
	}

	remaining, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		RequestedByType: "job",
		RequestedByID:   root.ID,
		Limit:           500,
		Offset:          500,
	})
	if err != nil {
		t.Fatalf("ListJobRuns for remaining children returned error: %v", err)
	}
	for _, child := range remaining {
		if _, err := store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{ID: child.ID}); err != nil {
			t.Fatalf("SucceedJobRun returned error: %v", err)
		}
	}

	ticker, err := New(Options{
		Store:  store,
		Logger: slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	if err != nil {
		t.Fatalf("New returned error: %v", err)
	}

	if _, err := ticker.Tick(ctx); err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}

	finalRoot, err := store.JobRuns().GetJobRun(ctx, root.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if finalRoot.State != storage.JobRunStateSucceeded {
		t.Fatalf("root state = %q, want succeeded", finalRoot.State)
	}
	if finalRoot.FinishedAt == nil {
		t.Fatal("root finished_at unset, want timestamp")
	}
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	t.Setenv(testdb.SchemaEnv, "relic_test_tracecompletion_"+schemaSuffix(t.Name()))
	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateTestStoreOnce.Do(func() {
		migrateTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
			return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateTestStoreErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateTestStoreErr))
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

func schemaSuffix(value string) string {
	value = strings.ToLower(value)
	var builder strings.Builder
	for _, char := range value {
		if (char >= 'a' && char <= 'z') || (char >= '0' && char <= '9') {
			builder.WriteRune(char)
			continue
		}
		builder.WriteRune('_')
	}

	return builder.String()
}
