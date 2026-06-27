package scan_bucket

import (
	"testing"

	syncbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/sync_bucket"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestParseScanInputMinimal(t *testing.T) {
	input, err := ParseScanInput(storage.JobRun{
		TargetType: "bucket",
		TargetID:   "bucket_abc",
		Input:      storage.JobRunPayload{},
	})
	if err != nil {
		t.Fatalf("ParseScanInput returned error: %v", err)
	}
	if input.BucketID != "bucket_abc" {
		t.Fatalf("BucketID = %q, want bucket_abc", input.BucketID)
	}
	if input.ScopePrefix != "" {
		t.Fatalf("ScopePrefix = %q, want empty", input.ScopePrefix)
	}
}

func TestParseScanInputWithPrefix(t *testing.T) {
	input, err := ParseScanInput(storage.JobRun{
		Input: storage.JobRunPayload{
			"bucket_id": "bucket_abc",
			"prefix":    "batch/",
		},
	})
	if err != nil {
		t.Fatalf("ParseScanInput returned error: %v", err)
	}
	if input.ScopePrefix != "batch/" {
		t.Fatalf("ScopePrefix = %q, want batch/", input.ScopePrefix)
	}
}

func TestParseScanInputRejectsMissingBucket(t *testing.T) {
	_, err := ParseScanInput(storage.JobRun{
		ID:    "jobrun_test",
		Input: storage.JobRunPayload{},
	})
	if err == nil {
		t.Fatal("ParseScanInput returned nil error, want missing bucket error")
	}
}

func TestObjectScopeParamsJoinsBucketAndScanPrefix(t *testing.T) {
	scope := ObjectScopeParams("bucket_abc", "raw/", ScanBucketInput{ScopePrefix: "batch/"})
	if scope.BucketID != "bucket_abc" {
		t.Fatalf("BucketID = %q, want bucket_abc", scope.BucketID)
	}
	want := syncbucket.EffectiveListPrefix("raw/", "batch/")
	if scope.Prefix != want {
		t.Fatalf("Prefix = %q, want %q", scope.Prefix, want)
	}
}
