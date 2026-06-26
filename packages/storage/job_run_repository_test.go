package storage

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestJobRunStoreCreateGetList(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	targetID := "bucket_job_run_create_" + time.Now().Format("20060102150405.000000000")
	created, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:            JobTypeSyncBucket,
		RequestedByType: "api",
		TargetType:      "bucket",
		TargetID:        targetID,
		Input: JobRunPayload{
			"bucket_id": targetID,
			"prefix":    "imports/",
		},
		MaxAttempts: 3,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE id = $1", created.ID)
	})

	if created.ID == "" {
		t.Fatal("created job run ID is empty")
	}
	if created.State != JobRunStatePending {
		t.Fatalf("created state = %q, want %q", created.State, JobRunStatePending)
	}
	if created.Attempt != 1 {
		t.Fatalf("created attempt = %d, want 1", created.Attempt)
	}
	if created.MaxAttempts != 3 {
		t.Fatalf("created max attempts = %d, want 3", created.MaxAttempts)
	}
	if created.Input["bucket_id"] != targetID {
		t.Fatalf("created bucket_id = %#v, want %q", created.Input["bucket_id"], targetID)
	}

	got, err := jobRuns.GetJobRun(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if got.ID != created.ID {
		t.Fatalf("got ID = %q, want %q", got.ID, created.ID)
	}

	listed, err := jobRuns.ListJobRuns(ctx, ListJobRunsParams{
		Type:       JobTypeSyncBucket,
		State:      JobRunStatePending,
		TargetType: "bucket",
		TargetID:   targetID,
		Limit:      50,
	})
	if err != nil {
		t.Fatalf("ListJobRuns returned error: %v", err)
	}
	if !jobRunListContains(listed, created.ID) {
		t.Fatalf("ListJobRuns did not include created job run %q", created.ID)
	}
}

func TestJobRunStoreGetMissing(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	_, err := store.JobRuns().GetJobRun(ctx, "jobrun_missing")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("GetJobRun error = %v, want %v", err, ErrNotFound)
	}
}

func TestJobRunStoreClaimProgressAndSucceed(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	errRollback := errors.New("rollback test transaction")
	err := store.WithTx(ctx, func(ctx context.Context, tx *Tx) error {
		if _, err := tx.tx.Exec(ctx, "UPDATE job_runs SET available_at = now() + interval '1 year' WHERE state = 'pending'"); err != nil {
			t.Fatalf("isolate pending job runs: %v", err)
		}

		jobRuns := tx.JobRuns()
		created, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
			Type:       JobTypeSyncBucket,
			TargetType: "bucket",
			TargetID:   "bucket_claim_test",
			Input: JobRunPayload{
				"bucket_id": "bucket_claim_test",
			},
		})
		if err != nil {
			t.Fatalf("CreateJobRun returned error: %v", err)
		}

		claimed, err := jobRuns.ClaimJobRun(ctx, ClaimJobRunParams{WorkerID: "worker-test"})
		if err != nil {
			t.Fatalf("ClaimJobRun returned error: %v", err)
		}
		if claimed.ID != created.ID {
			t.Fatalf("claimed ID = %q, want %q", claimed.ID, created.ID)
		}
		if claimed.State != JobRunStateRunning {
			t.Fatalf("claimed state = %q, want %q", claimed.State, JobRunStateRunning)
		}
		if claimed.LockedBy != "worker-test" {
			t.Fatalf("locked by = %q, want worker-test", claimed.LockedBy)
		}
		if claimed.StartedAt == nil || claimed.LockedAt == nil {
			t.Fatal("claimed run is missing start or lock timestamp")
		}

		progressed, err := jobRuns.UpdateJobRunProgress(ctx, UpdateJobRunProgressParams{
			ID: claimed.ID,
			Progress: JobRunPayload{
				"objects_seen": 12,
			},
		})
		if err != nil {
			t.Fatalf("UpdateJobRunProgress returned error: %v", err)
		}
		if progressed.Progress["objects_seen"] != float64(12) {
			t.Fatalf("objects_seen = %#v, want 12", progressed.Progress["objects_seen"])
		}

		succeeded, err := jobRuns.SucceedJobRun(ctx, SucceedJobRunParams{
			ID: claimed.ID,
			Result: JobRunPayload{
				"objects_synced": 12,
			},
		})
		if err != nil {
			t.Fatalf("SucceedJobRun returned error: %v", err)
		}
		if succeeded.State != JobRunStateSucceeded {
			t.Fatalf("succeeded state = %q, want %q", succeeded.State, JobRunStateSucceeded)
		}
		if succeeded.FinishedAt == nil {
			t.Fatal("succeeded run is missing finished timestamp")
		}
		if succeeded.LockedBy != "" || succeeded.LockedAt != nil {
			t.Fatal("succeeded run still has lock fields")
		}

		return errRollback
	})
	if !errors.Is(err, errRollback) {
		t.Fatalf("WithTx error = %v, want rollback sentinel", err)
	}
}

func TestJobRunStoreRetryAndFail(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	jobRuns := store.JobRuns()
	created, err := jobRuns.CreateJobRun(ctx, CreateJobRunParams{
		Type:        JobTypeSyncBucket,
		TargetType:  "bucket",
		TargetID:    "bucket_retry_test",
		MaxAttempts: 2,
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE id = $1", created.ID)
	})

	retryAt := time.Now().Add(time.Minute)
	retried, err := jobRuns.RetryJobRun(ctx, RetryJobRunParams{
		ID:           created.ID,
		ErrorMessage: "temporary upstream error",
		AvailableAt:  &retryAt,
	})
	if err != nil {
		t.Fatalf("RetryJobRun returned error: %v", err)
	}
	if retried.State != JobRunStatePending {
		t.Fatalf("retried state = %q, want %q", retried.State, JobRunStatePending)
	}
	if retried.Attempt != 2 {
		t.Fatalf("retried attempt = %d, want 2", retried.Attempt)
	}

	failed, err := jobRuns.FailJobRun(ctx, FailJobRunParams{
		ID:           created.ID,
		ErrorMessage: "permanent upstream error",
	})
	if err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}
	if failed.State != JobRunStateFailed {
		t.Fatalf("failed state = %q, want %q", failed.State, JobRunStateFailed)
	}
	if failed.ErrorMessage != "permanent upstream error" {
		t.Fatalf("failed error message = %q, want permanent upstream error", failed.ErrorMessage)
	}
}

func jobRunListContains(runs []JobRun, id string) bool {
	for _, run := range runs {
		if run.ID == id {
			return true
		}
	}

	return false
}
