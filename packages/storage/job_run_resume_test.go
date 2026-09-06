package storage

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestFindResumableSyncJobRunReturnsLatestFailedCheckpoint(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:                 "resume-sync-" + time.Now().Format("20060102150405.000000000"),
		Upstream:             BucketUpstreamS3,
		EndpointURL:          "https://s3.example.test",
		Region:               "us-east-1",
		BucketName:           "resume-sync-data",
		EncryptedCredentials: secretsEnvelope(),
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE target_id = $1", bucket.ID)
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", bucket.ID)
	})

	run, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input:      JobRunPayload{"bucket_id": bucket.ID},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().UpdateJobRunProgress(ctx, UpdateJobRunProgressParams{
		ID: run.ID,
		Progress: JobRunPayload{
			"phase":            "listing",
			"objects_listed":   int64(59000),
			"listing_complete": false,
			"listing_checkpoint": map[string]any{
				"continuation_token": "token-590",
				"objects_listed":     int64(59000),
				"listing_complete":   false,
			},
		},
	}); err != nil {
		t.Fatalf("UpdateJobRunProgress returned error: %v", err)
	}
	if _, err := store.JobRuns().FailJobRun(ctx, FailJobRunParams{
		ID:           run.ID,
		ErrorMessage: "upstream list timeout",
	}); err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}

	resumable, err := store.JobRuns().FindResumableSyncJobRun(ctx, FindResumableSyncJobRunParams{
		TargetType:  "bucket",
		TargetID:    bucket.ID,
		ScopePrefix: "",
	})
	if err != nil {
		t.Fatalf("FindResumableSyncJobRun returned error: %v", err)
	}
	if resumable.ID != run.ID {
		t.Fatalf("resumable id = %q, want %q", resumable.ID, run.ID)
	}
}

func TestFindResumableSyncJobRunIgnoresOlderFailedAfterNewerSync(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:                 "resume-sync-newer-" + time.Now().Format("20060102150405.000000000"),
		Upstream:             BucketUpstreamS3,
		EndpointURL:          "https://s3.example.test",
		Region:               "us-east-1",
		BucketName:           "resume-sync-newer-data",
		EncryptedCredentials: secretsEnvelope(),
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE target_id = $1", bucket.ID)
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", bucket.ID)
	})

	oldFailed, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input:      JobRunPayload{"bucket_id": bucket.ID},
	})
	if err != nil {
		t.Fatalf("CreateJobRun old failed returned error: %v", err)
	}
	if _, err := store.JobRuns().UpdateJobRunProgress(ctx, UpdateJobRunProgressParams{
		ID: oldFailed.ID,
		Progress: JobRunPayload{
			"objects_listed":   int64(1000),
			"listing_complete": false,
			"listing_checkpoint": map[string]any{
				"continuation_token": "token-1",
				"objects_listed":     int64(1000),
				"listing_complete":   false,
			},
		},
	}); err != nil {
		t.Fatalf("UpdateJobRunProgress returned error: %v", err)
	}
	if _, err := store.JobRuns().FailJobRun(ctx, FailJobRunParams{
		ID:           oldFailed.ID,
		ErrorMessage: "upstream list timeout",
	}); err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}

	newer, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input:      JobRunPayload{"bucket_id": bucket.ID},
	})
	if err != nil {
		t.Fatalf("CreateJobRun newer returned error: %v", err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{
		ID:     newer.ID,
		Result: JobRunPayload{"objects_seen": int64(42)},
	}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	_, err = store.JobRuns().FindResumableSyncJobRun(ctx, FindResumableSyncJobRunParams{
		TargetType:  "bucket",
		TargetID:    bucket.ID,
		ScopePrefix: "",
	})
	if !errorsIsNotFound(err) {
		t.Fatalf("FindResumableSyncJobRun error = %v, want not found", err)
	}
}

func TestFindResumableSyncJobRunIgnoresPartitionScopedSync(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:                 "resume-sync-partition-" + time.Now().Format("20060102150405.000000000"),
		Upstream:             BucketUpstreamS3,
		EndpointURL:          "https://s3.example.test",
		Region:               "us-east-1",
		BucketName:           "resume-sync-partition-data",
		EncryptedCredentials: secretsEnvelope(),
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE target_id = $1", bucket.ID)
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", bucket.ID)
	})

	run, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: JobRunPayload{
			"bucket_id": bucket.ID,
			"partition": map[string]any{
				"scheme":  "hash",
				"modulus": 4,
				"index":   1,
			},
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().UpdateJobRunProgress(ctx, UpdateJobRunProgressParams{
		ID: run.ID,
		Progress: JobRunPayload{
			"objects_listed":   int64(100),
			"listing_complete": false,
			"listing_checkpoint": map[string]any{
				"continuation_token": "token-partition",
				"objects_listed":     int64(100),
				"listing_complete":   false,
			},
		},
	}); err != nil {
		t.Fatalf("UpdateJobRunProgress returned error: %v", err)
	}
	if _, err := store.JobRuns().FailJobRun(ctx, FailJobRunParams{
		ID:           run.ID,
		ErrorMessage: "upstream list timeout",
	}); err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}

	_, err = store.JobRuns().FindResumableSyncJobRun(ctx, FindResumableSyncJobRunParams{
		TargetType:  "bucket",
		TargetID:    bucket.ID,
		ScopePrefix: "",
	})
	if !errorsIsNotFound(err) {
		t.Fatalf("FindResumableSyncJobRun error = %v, want not found", err)
	}
}

func TestResumeJobRunRequeuesFailedSync(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	run, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   "bucket_resume_job_" + time.Now().Format("20060102150405.000000000"),
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM job_runs WHERE trace_id = $1", run.TraceID)
	})

	if _, err := store.JobRuns().UpdateJobRunProgress(ctx, UpdateJobRunProgressParams{
		ID: run.ID,
		Progress: JobRunPayload{
			"objects_listed": int64(59000),
			"listing_checkpoint": map[string]any{
				"continuation_token": "token-590",
				"objects_listed":     int64(59000),
			},
		},
	}); err != nil {
		t.Fatalf("UpdateJobRunProgress returned error: %v", err)
	}
	if _, err := store.JobRuns().FailJobRun(ctx, FailJobRunParams{
		ID:           run.ID,
		ErrorMessage: "upstream list timeout",
	}); err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}

	resumed, err := store.JobRuns().ResumeJobRun(ctx, run.ID)
	if err != nil {
		t.Fatalf("ResumeJobRun returned error: %v", err)
	}
	if resumed.State != JobRunStatePending {
		t.Fatalf("state = %q, want pending", resumed.State)
	}
	if resumed.ErrorMessage != "" {
		t.Fatalf("error_message = %q, want empty", resumed.ErrorMessage)
	}
	if resumed.FinishedAt != nil {
		t.Fatalf("finished_at = %v, want nil", resumed.FinishedAt)
	}
	if storagePayloadInt64(resumed.Progress, "objects_listed") != 59000 {
		t.Fatalf("objects_listed = %d, want 59000", storagePayloadInt64(resumed.Progress, "objects_listed"))
	}
}

func errorsIsNotFound(err error) bool {
	return errors.Is(err, ErrNotFound)
}

func storagePayloadInt64(payload JobRunPayload, key string) int64 {
	return PayloadInt64(payload, key)
}

func TestResumeRootRequeuesFailedChildrenAndPreservesSucceededChildren(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()
	root, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{Type: JobTypeSyncBucket})
	if err != nil {
		t.Fatal(err)
	}
	failed, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{Type: JobTypeImportObjects, RequestedByType: "job", RequestedByID: root.ID})
	if err != nil {
		t.Fatal(err)
	}
	done, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{Type: JobTypeImportObjects, RequestedByType: "job", RequestedByID: root.ID})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{ID: done.ID}); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{root.ID, failed.ID} {
		if _, err := store.JobRuns().FailJobRun(ctx, FailJobRunParams{ID: id, ErrorMessage: "interrupted"}); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := store.JobRuns().ResumeJobRun(ctx, root.ID); err != nil {
		t.Fatal(err)
	}
	for id, want := range map[string]JobRunState{root.ID: JobRunStatePending, failed.ID: JobRunStatePending, done.ID: JobRunStateSucceeded} {
		run, err := store.JobRuns().GetJobRun(ctx, id)
		if err != nil || run.State != want {
			t.Fatalf("run %s state=%s want=%s err=%v", id, run.State, want, err)
		}
	}
}
