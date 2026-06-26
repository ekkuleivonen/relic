package sync_bucket

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestBucketIDUsesInputBucketID(t *testing.T) {
	bucketID, err := BucketID(storage.JobRun{
		ID: "jobrun_test",
		Input: storage.JobRunPayload{
			"bucket_id": "bucket_from_input",
		},
		TargetType: "bucket",
		TargetID:   "bucket_from_target",
	})
	if err != nil {
		t.Fatalf("BucketID returned error: %v", err)
	}
	if bucketID != "bucket_from_input" {
		t.Fatalf("bucketID = %q, want bucket_from_input", bucketID)
	}
}

func TestBucketIDFallsBackToTarget(t *testing.T) {
	bucketID, err := BucketID(storage.JobRun{
		ID:         "jobrun_test",
		Input:      storage.JobRunPayload{},
		TargetType: "bucket",
		TargetID:   "bucket_from_target",
	})
	if err != nil {
		t.Fatalf("BucketID returned error: %v", err)
	}
	if bucketID != "bucket_from_target" {
		t.Fatalf("bucketID = %q, want bucket_from_target", bucketID)
	}
}

func TestBucketIDRejectsMissingBucket(t *testing.T) {
	_, err := BucketID(storage.JobRun{
		ID:    "jobrun_test",
		Input: storage.JobRunPayload{},
	})
	if err == nil {
		t.Fatal("BucketID returned nil error, want missing bucket error")
	}
}
