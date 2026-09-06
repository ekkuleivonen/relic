package scheduler

import (
	"context"
	"testing"
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/settings"
	"github.com/elei-io/pithosys/packages/storage"
)

func TestDuplicateDetectionSchedulerTickEnqueuesWhenDue(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	scheduler, err := NewDuplicateDetectionScheduler(DuplicateDetectionSchedulerOptions{
		Store: store,
		Now:   func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: settings.Static{
			storage.SettingDuplicateDetectionInterval: "1h",
		},
	})
	if err != nil {
		t.Fatalf("NewDuplicateDetectionScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if !enqueued {
		t.Fatal("expected duplicate detection job to be enqueued")
	}

	runs, err := store.JobRuns().ListJobRuns(ctx, storage.ListJobRunsParams{
		Type:       storage.JobTypeDetectDuplicates,
		TargetType: detectDuplicatesTargetType,
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("job count = %d, want 1", len(runs))
	}
	if runs[0].RequestedByType != "scheduler" {
		t.Fatalf("requested_by_type = %q, want scheduler", runs[0].RequestedByType)
	}
}

func TestDuplicateDetectionSchedulerTickDedupesActiveRun(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeDetectDuplicates,
		TargetType: detectDuplicatesTargetType,
		TargetID:   detectDuplicatesTargetID,
	}); err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	scheduler, err := NewDuplicateDetectionScheduler(DuplicateDetectionSchedulerOptions{
		Store:    store,
		Now:      func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: settings.Static(settings.StaticFromRegistry()),
	})
	if err != nil {
		t.Fatalf("NewDuplicateDetectionScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued {
		t.Fatal("expected no duplicate detection job while one is active")
	}
}

func TestDuplicateDetectionSchedulerTickDedupesLegacyNullTargetRun(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeDetectDuplicates,
		TargetType: detectDuplicatesTargetType,
	}); err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	scheduler, err := NewDuplicateDetectionScheduler(DuplicateDetectionSchedulerOptions{
		Store:    store,
		Now:      func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: settings.Static(settings.StaticFromRegistry()),
	})
	if err != nil {
		t.Fatalf("NewDuplicateDetectionScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued {
		t.Fatal("expected no duplicate detection job while a legacy null-target run is active")
	}
}

func TestDuplicateDetectionSchedulerTickSkipsWhenNotDue(t *testing.T) {
	ctx := context.Background()
	store, cleanup := schedulerTestStore(t, ctx)
	defer cleanup()

	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeDetectDuplicates,
		TargetType: detectDuplicatesTargetType,
		TargetID:   detectDuplicatesTargetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{
		ID:     run.ID,
		Result: storage.JobRunPayload{"verified_groups": 0},
	}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	scheduler, err := NewDuplicateDetectionScheduler(DuplicateDetectionSchedulerOptions{
		Store: store,
		Now:   func() time.Time { return time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC) },
		Settings: settings.Static{
			storage.SettingDuplicateDetectionInterval: "24h",
		},
	})
	if err != nil {
		t.Fatalf("NewDuplicateDetectionScheduler returned error: %v", err)
	}

	enqueued, err := scheduler.Tick(ctx)
	if err != nil {
		t.Fatalf("Tick returned error: %v", err)
	}
	if enqueued {
		t.Fatal("expected duplicate detection job to be skipped before interval elapsed")
	}
}

func TestDecideDuplicateDetection(t *testing.T) {
	now := time.Date(2026, 6, 28, 12, 0, 0, 0, time.UTC)
	lastFinished := now.Add(-12 * time.Hour)

	if !DecideDuplicateDetection(nil, now, time.Hour) {
		t.Fatal("expected enqueue when never run")
	}
	if DecideDuplicateDetection(&lastFinished, now, 24*time.Hour) {
		t.Fatal("expected skip before interval elapsed")
	}
	if !DecideDuplicateDetection(&lastFinished, now, time.Hour) {
		t.Fatal("expected enqueue after interval elapsed")
	}
}
