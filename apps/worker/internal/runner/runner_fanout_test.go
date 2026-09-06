package runner

import (
	"context"
	"io"
	"log/slog"
	"testing"

	workerjobs "github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/apps/worker/internal/settings"
	"github.com/ekkuleivonen/relic/apps/worker/internal/tracecompletion"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestRunnerDefersCompletionForFanOutJobs(t *testing.T) {
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

	runner := newTestRunner(t, store, fanOutHandler{jobType: storage.JobTypeCleanupRuns})
	claimed, err := runner.RunOnce(ctx)
	if err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	if !claimed {
		t.Fatal("claimed = false, want true")
	}

	updated, err := store.JobRuns().GetJobRun(ctx, run.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if updated.State != storage.JobRunStateRunning {
		t.Fatalf("state = %q, want running", updated.State)
	}
	if !storage.PayloadBool(updated.Result, workerjobs.ResultKeyAwaitChildren) {
		t.Fatalf("result = %#v, want await_children true", updated.Result)
	}
	if updated.FinishedAt != nil {
		t.Fatal("finished_at set, want nil while awaiting children")
	}
}

func TestRunnerFinalizesAwaitingTraceAfterChildrenComplete(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()
	clearJobRuns(t, ctx)
	t.Cleanup(func() {
		clearJobRuns(t, context.Background())
	})

	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type: storage.JobTypeSyncBucket,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	child, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	claimed, err := store.JobRuns().ClaimJobRun(ctx, storage.ClaimJobRunParams{
		WorkerID: "test-worker",
		Types:    []storage.JobType{storage.JobTypeSyncBucket},
	})
	if err != nil {
		t.Fatalf("ClaimJobRun returned error: %v", err)
	}
	if claimed.ID != root.ID {
		t.Fatalf("claimed job = %q, want %q", claimed.ID, root.ID)
	}

	result := workerjobs.FanOutResult(map[string][]string{
		"import_objects": {child.ID},
	}, storage.JobRunPayload{
		"objects_seen":         int64(1),
		"import_objects_count": 1,
	})
	if _, err := store.JobRuns().AwaitJobRunChildren(ctx, storage.AwaitJobRunChildrenParams{
		ID:       root.ID,
		Result:   result,
		Progress: workerjobs.FanOutProgress(result),
	}); err != nil {
		t.Fatalf("AwaitJobRunChildren returned error: %v", err)
	}

	if _, err := store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{
		ID: child.ID,
		Result: storage.JobRunPayload{
			"objects_imported": 1,
		},
	}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	ticker, err := tracecompletion.New(tracecompletion.Options{Store: store})
	if err != nil {
		t.Fatalf("New trace completion ticker returned error: %v", err)
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

type fanOutHandler struct {
	jobType storage.JobType
}

func (h fanOutHandler) Type() storage.JobType {
	return h.jobType
}

func (h fanOutHandler) Handle(context.Context, storage.JobRun) (storage.JobRunPayload, error) {
	return workerjobs.FanOutResult(map[string][]string{
		"import_objects": {"jobrun_child"},
	}, storage.JobRunPayload{
		"objects_seen":         int64(1),
		"import_objects_count": 1,
	}), nil
}

func newTestRunner(t *testing.T, store *storage.Store, handler workerjobs.Handler) *Runner {
	t.Helper()

	registry, err := workerjobs.NewRegistry(handler)
	if err != nil {
		t.Fatalf("NewRegistry returned error: %v", err)
	}
	runner, err := New(Options{
		Store:    store,
		Registry: registry,
		WorkerID: "test-worker",
		Settings: settings.Static{"WORKER_RUNNER_POLL_INTERVAL": "1ms", "WORKER_RUNNER_RETRY_DELAY": "1ms"},
		Logger:   slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	if err != nil {
		t.Fatalf("New returned error: %v", err)
	}

	return runner
}
