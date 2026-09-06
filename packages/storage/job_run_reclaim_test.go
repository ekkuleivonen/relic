package storage

import (
	"context"
	"testing"
	"time"
)

func TestReclaimStaleLockedJobsFailsAbandonedRuns(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	run, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   "bucket_stale_reclaim_" + time.Now().Format("20060102150405.000000000"),
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", run.TraceID)
	})

	if _, err := jobRuns.ClaimJobRun(ctx, ClaimJobRunParams{WorkerID: "stale-worker"}); err != nil {
		t.Fatalf("ClaimJobRun returned error: %v", err)
	}

	staleAt := time.Now().Add(-30 * time.Minute)
	if _, err := store.pool.Exec(ctx, `
		UPDATE job_runs
		SET updated_at = $2
		WHERE id = $1
	`, run.ID, staleAt); err != nil {
		t.Fatalf("backdate updated_at returned error: %v", err)
	}

	reclaimed, err := jobRuns.ReclaimStaleLockedJobs(ctx, ReclaimStaleLockedJobsParams{
		StaleAfter: 15 * time.Minute,
	})
	if err != nil {
		t.Fatalf("ReclaimStaleLockedJobs returned error: %v", err)
	}
	if reclaimed != 1 {
		t.Fatalf("reclaimed = %d, want 1", reclaimed)
	}

	failed, err := jobRuns.GetJobRun(ctx, run.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if failed.State != JobRunStateFailed {
		t.Fatalf("state = %q, want failed", failed.State)
	}
	if failed.LockedBy != "" {
		t.Fatalf("locked_by = %q, want empty", failed.LockedBy)
	}
	if failed.ErrorMessage != staleLockedJobErrorMessage {
		t.Fatalf("error_message = %q, want %q", failed.ErrorMessage, staleLockedJobErrorMessage)
	}
}

func TestHasActiveWorkForTargetIgnoresStaleLockedRuns(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_stale_active_" + time.Now().Format("20060102150405.000000000")
	run, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", run.TraceID)
	})

	if _, err := jobRuns.ClaimJobRun(ctx, ClaimJobRunParams{WorkerID: "stale-worker"}); err != nil {
		t.Fatalf("ClaimJobRun returned error: %v", err)
	}

	staleAt := time.Now().Add(-30 * time.Minute)
	if _, err := store.pool.Exec(ctx, `
		UPDATE job_runs
		SET updated_at = $2
		WHERE id = $1
	`, run.ID, staleAt); err != nil {
		t.Fatalf("backdate updated_at returned error: %v", err)
	}

	active, err := jobRuns.HasActiveWorkForTarget(ctx, HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   targetID,
		StaleAfter: 15 * time.Minute,
	})
	if err != nil {
		t.Fatalf("HasActiveWorkForTarget returned error: %v", err)
	}
	if active {
		t.Fatal("HasActiveWorkForTarget = true, want false for stale locked run")
	}
}
