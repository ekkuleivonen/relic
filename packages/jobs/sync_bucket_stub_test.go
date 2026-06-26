package jobs

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestSyncBucketIDUsesInputBucketID(t *testing.T) {
	bucketID, err := syncBucketID(storage.JobRun{
		ID: "jobrun_test",
		Input: storage.JobRunPayload{
			"bucket_id": "bucket_from_input",
		},
		TargetType: "bucket",
		TargetID:   "bucket_from_target",
	})
	if err != nil {
		t.Fatalf("syncBucketID returned error: %v", err)
	}
	if bucketID != "bucket_from_input" {
		t.Fatalf("bucketID = %q, want bucket_from_input", bucketID)
	}
}

func TestSyncBucketIDFallsBackToTarget(t *testing.T) {
	bucketID, err := syncBucketID(storage.JobRun{
		ID:         "jobrun_test",
		Input:      storage.JobRunPayload{},
		TargetType: "bucket",
		TargetID:   "bucket_from_target",
	})
	if err != nil {
		t.Fatalf("syncBucketID returned error: %v", err)
	}
	if bucketID != "bucket_from_target" {
		t.Fatalf("bucketID = %q, want bucket_from_target", bucketID)
	}
}

func TestSyncBucketIDRejectsMissingBucket(t *testing.T) {
	_, err := syncBucketID(storage.JobRun{
		ID:    "jobrun_test",
		Input: storage.JobRunPayload{},
	})
	if err == nil {
		t.Fatal("syncBucketID returned nil error, want missing bucket error")
	}
}
