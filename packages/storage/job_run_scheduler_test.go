package storage

import (
	"context"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/secrets"
)

func TestJobRunStoreHasActiveJobRunReturnsTrueForPendingScan(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:        "active-scan-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "example-data",
		EncryptedCredentials: secretsEnvelope(),
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", bucket.ID)
	})

	_, err = store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	active, err := store.JobRuns().HasActiveJobRun(ctx, HasActiveJobRunParams{
		Type:       JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
	})
	if err != nil {
		t.Fatalf("HasActiveJobRun returned error: %v", err)
	}
	if !active {
		t.Fatal("HasActiveJobRun = false, want true for pending scan")
	}
}

func TestJobRunStoreHasActiveJobRunIgnoresCompletedScans(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:        "completed-scan-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "example-data",
		EncryptedCredentials: secretsEnvelope(),
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", bucket.ID)
	})

	run, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{
		ID:     run.ID,
		Result: JobRunPayload{"status": "healthy"},
	}); err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	active, err := store.JobRuns().HasActiveJobRun(ctx, HasActiveJobRunParams{
		Type:       JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
	})
	if err != nil {
		t.Fatalf("HasActiveJobRun returned error: %v", err)
	}
	if active {
		t.Fatal("HasActiveJobRun = true, want false for succeeded scan")
	}
}

func TestJobRunStoreLastSucceededJobRunFinishedAt(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:        "last-scan-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "example-data",
		EncryptedCredentials: secretsEnvelope(),
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM buckets WHERE id = $1", bucket.ID)
	})

	run, err := store.JobRuns().CreateJobRun(ctx, CreateJobRunParams{
		Type:       JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	succeeded, err := store.JobRuns().SucceedJobRun(ctx, SucceedJobRunParams{
		ID:     run.ID,
		Result: JobRunPayload{"status": "healthy"},
	})
	if err != nil {
		t.Fatalf("SucceedJobRun returned error: %v", err)
	}

	finishedAt, err := store.JobRuns().LastSucceededJobRunFinishedAt(ctx, LastSucceededJobRunFinishedAtParams{
		Type:       JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
	})
	if err != nil {
		t.Fatalf("LastSucceededJobRunFinishedAt returned error: %v", err)
	}
	if finishedAt == nil {
		t.Fatal("LastSucceededJobRunFinishedAt returned nil, want timestamp")
	}
	if succeeded.FinishedAt == nil || !finishedAt.Equal(*succeeded.FinishedAt) {
		t.Fatalf("finishedAt = %v, want %v", finishedAt, succeeded.FinishedAt)
	}
}

func secretsEnvelope() secrets.Envelope {
	return secrets.Envelope{
		KeyID:      "local-dev",
		Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
		Nonce:      []byte("012345678901234567890123"),
		Ciphertext: []byte("encrypted-credentials"),
	}
}
