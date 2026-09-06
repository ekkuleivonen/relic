package storage

import (
	"context"
	"testing"
)

func TestJobRunStoreAwaitAndFinalizeAwaitingJob(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	root, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type: JobTypeSyncBucket,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", root.TraceID)
	})

	if _, err := store.JobRuns().ClaimJobRun(ctx, ClaimJobRunParams{WorkerID: "test-worker"}); err != nil {
		t.Fatalf("ClaimJobRun returned error: %v", err)
	}

	result := JobRunPayload{
		"await_children": true,
		"child_job_ids": map[string]any{
			"import_objects": []any{"jobrun_child"},
		},
		"objects_seen":         int64(2),
		"import_objects_count": int64(2),
	}
	awaiting, err := store.JobRuns().AwaitJobRunChildren(ctx, AwaitJobRunChildrenParams{
		ID:       root.ID,
		Result:   result,
		Progress: TraceProgressRollup(TraceSummary{Phase: "applying"}),
	})
	if err != nil {
		t.Fatalf("AwaitJobRunChildren returned error: %v", err)
	}
	if awaiting.State != JobRunStateRunning {
		t.Fatalf("state = %q, want running", awaiting.State)
	}
	if awaiting.LockedBy != "" {
		t.Fatalf("locked_by = %q, want empty", awaiting.LockedBy)
	}

	child, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{
		ID: child.ID,
		Result: JobRunPayload{
			"objects_imported": 2,
		},
	}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	complete, err := store.JobRuns().DirectChildrenComplete(ctx, root.ID)
	if err != nil {
		t.Fatalf("DirectChildrenComplete returned error: %v", err)
	}
	if !complete {
		t.Fatal("DirectChildrenComplete() = false, want true")
	}

	summary, err := store.JobRuns().SummarizeTrace(ctx, root.TraceID)
	if err != nil {
		t.Fatalf("SummarizeTrace returned error: %v", err)
	}
	finalized, err := store.JobRuns().FinalizeAwaitingJob(ctx, awaiting, summary)
	if err != nil {
		t.Fatalf("FinalizeAwaitingJob returned error: %v", err)
	}
	if !finalized {
		t.Fatal("FinalizeAwaitingJob = false, want true")
	}

	completed, err := store.JobRuns().GetJobRun(ctx, root.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if completed.State != JobRunStateSucceeded {
		t.Fatalf("state = %q, want succeeded", completed.State)
	}
}

func TestDirectChildrenCompleteRequiresTerminalChildStates(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	parent, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type: JobTypeSyncBucket,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", parent.TraceID)
	})

	child, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   parent.ID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	complete, err := store.JobRuns().DirectChildrenComplete(ctx, parent.ID)
	if err != nil {
		t.Fatalf("DirectChildrenComplete returned error: %v", err)
	}
	if complete {
		t.Fatal("DirectChildrenComplete() = true, want false while child pending")
	}

	if _, err := store.JobRuns().ClaimJobRun(ctx, ClaimJobRunParams{WorkerID: "test-worker"}); err != nil {
		t.Fatalf("ClaimJobRun returned error: %v", err)
	}

	complete, err = store.JobRuns().DirectChildrenComplete(ctx, parent.ID)
	if err != nil {
		t.Fatalf("DirectChildrenComplete returned error: %v", err)
	}
	if complete {
		t.Fatal("DirectChildrenComplete() = true, want false while child running")
	}

	if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{ID: child.ID}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	complete, err = store.JobRuns().DirectChildrenComplete(ctx, parent.ID)
	if err != nil {
		t.Fatalf("DirectChildrenComplete returned error: %v", err)
	}
	if !complete {
		t.Fatal("DirectChildrenComplete() = false, want true after child succeeded")
	}
}

func TestDirectChildrenCompleteScalesBeyondListCap(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	parent, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type: JobTypeSyncBucket,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", parent.TraceID)
	})

	const childCount = 600
	for range childCount {
		if _, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
			Type:            JobTypeImportObjects,
			RequestedByType: "job",
			RequestedByID:   parent.ID,
		}); err != nil {
			t.Fatalf("CreateJobRun returned error: %v", err)
		}
	}

	complete, err := store.JobRuns().DirectChildrenComplete(ctx, parent.ID)
	if err != nil {
		t.Fatalf("DirectChildrenComplete returned error: %v", err)
	}
	if complete {
		t.Fatal("DirectChildrenComplete() = true, want false with pending children")
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, ListJobRunsParams{
		TraceID: parent.TraceID,
		Limit:   500,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 500 {
		t.Fatalf("listed runs = %d, want 500 cap", len(runs))
	}

	children, err := store.JobRuns().ListJobRuns(ctx, ListJobRunsParams{
		RequestedByType: "job",
		RequestedByID:   parent.ID,
		Limit:           500,
	})
	if err != nil {
		t.Fatalf("ListJobRuns for children returned error: %v", err)
	}
	for _, child := range children {
		if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{ID: child.ID}); err != nil {
			t.Fatalf("SucceedJobRun returned error: %v", err)
		}
	}

	complete, err = store.JobRuns().DirectChildrenComplete(ctx, parent.ID)
	if err != nil {
		t.Fatalf("DirectChildrenComplete returned error: %v", err)
	}
	if complete {
		t.Fatal("DirectChildrenComplete() = true, want false with remaining pending children")
	}

	remaining, err := store.JobRuns().ListJobRuns(ctx, ListJobRunsParams{
		RequestedByType: "job",
		RequestedByID:   parent.ID,
		Limit:           500,
		Offset:          500,
	})
	if err != nil {
		t.Fatalf("ListJobRuns for remaining children returned error: %v", err)
	}
	for _, child := range remaining {
		if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{ID: child.ID}); err != nil {
			t.Fatalf("SucceedJobRun returned error: %v", err)
		}
	}

	complete, err = store.JobRuns().DirectChildrenComplete(ctx, parent.ID)
	if err != nil {
		t.Fatalf("DirectChildrenComplete returned error: %v", err)
	}
	if !complete {
		t.Fatal("DirectChildrenComplete() = false, want true after all children succeeded")
	}
}

func TestFinalizeAwaitingJobScalesBeyondListCap(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	root, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type: JobTypeSyncBucket,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", root.TraceID)
	})

	if _, err := store.JobRuns().ClaimJobRun(ctx, ClaimJobRunParams{WorkerID: "test-worker"}); err != nil {
		t.Fatalf("ClaimJobRun returned error: %v", err)
	}

	result := JobRunPayload{
		"await_children":       true,
		"objects_seen":         int64(600),
		"import_objects_count": int64(600),
	}
	awaiting, err := store.JobRuns().AwaitJobRunChildren(ctx, AwaitJobRunChildrenParams{
		ID:     root.ID,
		Result: result,
		Progress: JobRunPayload{
			"phase":                "importing",
			"objects_listed":       int64(600),
			"import_objects_count": int64(600),
		},
	})
	if err != nil {
		t.Fatalf("AwaitJobRunChildren returned error: %v", err)
	}

	const childCount = 600
	for range childCount {
		if _, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
			Type:            JobTypeImportObjects,
			RequestedByType: "job",
			RequestedByID:   root.ID,
		}); err != nil {
			t.Fatalf("CreateJobRun returned error: %v", err)
		}
	}

	succeedChildren := func(offset int) {
		t.Helper()

		children, err := store.JobRuns().ListJobRuns(ctx, ListJobRunsParams{
			RequestedByType: "job",
			RequestedByID:   root.ID,
			Limit:           500,
			Offset:          offset,
		})
		if err != nil {
			t.Fatalf("ListJobRuns returned error: %v", err)
		}
		for _, child := range children {
			if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{ID: child.ID}); err != nil {
				t.Fatalf("SucceedJobRun returned error: %v", err)
			}
		}
	}

	succeedChildren(0)

	finalized, err := store.JobRuns().FinalizeAwaitingJob(ctx, awaiting, TraceSummary{})
	if err != nil {
		t.Fatalf("FinalizeAwaitingJob returned error: %v", err)
	}
	if finalized {
		t.Fatal("FinalizeAwaitingJob = true, want false before all children succeed")
	}

	succeedChildren(500)

	summary, err := store.JobRuns().SummarizeTrace(ctx, root.TraceID)
	if err != nil {
		t.Fatalf("SummarizeTrace returned error: %v", err)
	}
	finalized, err = store.JobRuns().FinalizeAwaitingJob(ctx, awaiting, summary)
	if err != nil {
		t.Fatalf("FinalizeAwaitingJob returned error: %v", err)
	}
	if !finalized {
		t.Fatal("FinalizeAwaitingJob = false, want true after all children succeeded")
	}

	completed, err := store.JobRuns().GetJobRun(ctx, root.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if completed.State != JobRunStateSucceeded {
		t.Fatalf("state = %q, want succeeded", completed.State)
	}
}

func TestDirectChildrenFailedDetectsFailedChild(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	parent, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type: JobTypeSyncBucket,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", parent.TraceID)
	})

	child, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   parent.ID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().FailJobRun(ctx, FailJobRunParams{
		ID:           child.ID,
		ErrorMessage: "boom",
	}); err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}

	failed, err := store.JobRuns().DirectChildrenFailed(ctx, parent.ID)
	if err != nil {
		t.Fatalf("DirectChildrenFailed returned error: %v", err)
	}
	if !failed {
		t.Fatal("DirectChildrenFailed() = false, want true")
	}
}
