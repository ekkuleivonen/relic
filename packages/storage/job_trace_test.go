package storage

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestJobRunStoreCreateJobRunAssignsTraceID(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_trace_create_" + time.Now().Format("20060102150405.000000000")

	root, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeSyncBucket,
		RequestedByType: "user",
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun root returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", root.TraceID)
	})

	child, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun child returned error: %v", err)
	}

	if root.TraceID != root.ID {
		t.Fatalf("root trace_id = %q, want %q", root.TraceID, root.ID)
	}
	if child.TraceID != root.TraceID {
		t.Fatalf("child trace_id = %q, want %q", child.TraceID, root.TraceID)
	}

	byTrace, err := jobRuns.ListJobRuns(ctx, ListJobRunsParams{
		TraceID: root.TraceID,
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns by trace returned error: %v", err)
	}
	if len(byTrace) != 2 {
		t.Fatalf("trace job count = %d, want 2", len(byTrace))
	}
}

func TestJobRunStoreIsTraceActive(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_trace_active_" + time.Now().Format("20060102150405.000000000")

	root, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", root.TraceID)
	})

	active, err := jobRuns.IsTraceActive(ctx, root.TraceID)
	if err != nil {
		t.Fatalf("IsTraceActive returned error: %v", err)
	}
	if !active {
		t.Fatal("IsTraceActive = false, want true for pending root")
	}

	if _, err := jobRuns.SucceedJobRun(ctx, SucceedJobRunParams{ID: root.ID}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	active, err = jobRuns.IsTraceActive(ctx, root.TraceID)
	if err != nil {
		t.Fatalf("IsTraceActive after success returned error: %v", err)
	}
	if active {
		t.Fatal("IsTraceActive = true, want false after root succeeded")
	}
}

func TestJobRunStoreSummarizeTrace(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_trace_summary_" + time.Now().Format("20060102150405.000000000")

	root, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun root returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", root.TraceID)
	})

	if _, err := jobRuns.UpdateJobRunProgress(ctx, UpdateJobRunProgressParams{
		ID: root.ID,
		Progress: JobRunPayload{
			"phase":                 "importing",
			"objects_listed":        1000,
			"import_objects_count":  1000,
			"refresh_objects_count": 0,
			"remove_objects_count":  0,
		},
	}); err != nil {
		t.Fatalf("UpdateJobRunProgress returned error: %v", err)
	}

	doneChild, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun done child returned error: %v", err)
	}
	if _, err := jobRuns.SucceedJobRun(ctx, SucceedJobRunParams{
		ID: doneChild.ID,
		Result: JobRunPayload{
			"objects_imported": 500,
		},
	}); err != nil {
		t.Fatalf("SucceedJobRun done child returned error: %v", err)
	}

	if _, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	}); err != nil {
		t.Fatalf("CreateJobRun pending child returned error: %v", err)
	}

	summary, err := jobRuns.SummarizeTrace(ctx, root.TraceID)
	if err != nil {
		t.Fatalf("SummarizeTrace returned error: %v", err)
	}

	if summary.State != JobRunStateRunning {
		t.Fatalf("summary state = %q, want %q", summary.State, JobRunStateRunning)
	}
	if summary.Phase != "importing" {
		t.Fatalf("summary phase = %q, want importing", summary.Phase)
	}
	if summary.ObjectsListed != 1000 {
		t.Fatalf("summary objects_listed = %d, want 1000", summary.ObjectsListed)
	}
	if summary.ObjectsPlanned.Import != 1000 {
		t.Fatalf("summary planned import = %d, want 1000", summary.ObjectsPlanned.Import)
	}
	if summary.ObjectsApplied.Import != 500 {
		t.Fatalf("summary applied import = %d, want 500", summary.ObjectsApplied.Import)
	}
	if summary.Batches.Import.Total != 2 {
		t.Fatalf("summary import batches total = %d, want 2", summary.Batches.Import.Total)
	}
	if summary.Batches.Import.Done != 1 {
		t.Fatalf("summary import batches done = %d, want 1", summary.Batches.Import.Done)
	}
	if summary.Batches.Import.Pending != 1 {
		t.Fatalf("summary import batches pending = %d, want 1", summary.Batches.Import.Pending)
	}
}

func TestJobRunStoreSummarizeTraceMissing(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	_, err := store.JobRuns().SummarizeTrace(ctx, "jobrun_missing_trace")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("SummarizeTrace error = %v, want %v", err, ErrNotFound)
	}
}

func TestJobRunStoreHasActiveWorkForTarget(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_trace_target_" + time.Now().Format("20060102150405.000000000")

	root, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun root returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", root.TraceID)
	})

	active, err := jobRuns.HasActiveWorkForTarget(ctx, HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("HasActiveWorkForTarget returned error: %v", err)
	}
	if !active {
		t.Fatal("HasActiveWorkForTarget = false, want true")
	}

	child, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun child returned error: %v", err)
	}

	if _, err := jobRuns.SucceedJobRun(ctx, SucceedJobRunParams{ID: root.ID}); err != nil {
		t.Fatalf("SucceedJobRun root returned error: %v", err)
	}

	active, err = jobRuns.HasActiveWorkForTarget(ctx, HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("HasActiveWorkForTarget with child pending returned error: %v", err)
	}
	if !active {
		t.Fatal("HasActiveWorkForTarget = false, want true while child pending")
	}

	if _, err := jobRuns.SucceedJobRun(ctx, SucceedJobRunParams{ID: child.ID}); err != nil {
		t.Fatalf("SucceedJobRun child returned error: %v", err)
	}

	active, err = jobRuns.HasActiveWorkForTarget(ctx, HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("HasActiveWorkForTarget after completion returned error: %v", err)
	}
	if active {
		t.Fatal("HasActiveWorkForTarget = true, want false after trace complete")
	}
}

func TestJobRunStoreHasActiveWorkForTargetDetectsScanTraceSyncChild(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_scan_trace_target_" + time.Now().Format("20060102150405.000000000")

	scanRoot, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun scan root returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", scanRoot.TraceID)
	})

	syncChild, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeSyncBucket,
		RequestedByType: "job",
		RequestedByID:   scanRoot.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun sync child returned error: %v", err)
	}

	if _, err := jobRuns.SucceedJobRun(ctx, SucceedJobRunParams{ID: scanRoot.ID}); err != nil {
		t.Fatalf("SucceedJobRun scan root returned error: %v", err)
	}

	active, err := jobRuns.HasActiveWorkForTarget(ctx, HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("HasActiveWorkForTarget returned error: %v", err)
	}
	if !active {
		t.Fatal("HasActiveWorkForTarget = false, want true while scan-escalated sync child is pending")
	}

	if _, err := jobRuns.SucceedJobRun(ctx, SucceedJobRunParams{ID: syncChild.ID}); err != nil {
		t.Fatalf("SucceedJobRun sync child returned error: %v", err)
	}

	active, err = jobRuns.HasActiveWorkForTarget(ctx, HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("HasActiveWorkForTarget after sync child completion returned error: %v", err)
	}
	if active {
		t.Fatal("HasActiveWorkForTarget = true, want false after sync child completes")
	}
}

func TestJobRunStoreHasActiveWorkForTargetIgnoresStandaloneUpstreamImports(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_upstream_import_target_" + time.Now().Format("20060102150405.000000000")

	importRun, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeImportObjects,
		RequestedByType: "upstream_event",
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun import returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", importRun.TraceID)
	})

	active, err := jobRuns.HasActiveWorkForTarget(ctx, HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("HasActiveWorkForTarget returned error: %v", err)
	}
	if active {
		t.Fatal("HasActiveWorkForTarget = true, want false for standalone upstream import")
	}
}
