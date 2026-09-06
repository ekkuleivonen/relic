package scan_bucket

import (
	"fmt"

	syncbucket "github.com/elei-io/pithosys/apps/worker/internal/jobs/sync_bucket"
	"github.com/elei-io/pithosys/packages/storage"
)

type ScanBucketInput struct {
	BucketID    string
	ScopePrefix string
}

func ParseScanInput(run storage.JobRun) (ScanBucketInput, error) {
	bucketID, err := BucketID(run)
	if err != nil {
		return ScanBucketInput{}, err
	}

	input := ScanBucketInput{
		BucketID: bucketID,
	}
	if scopePrefix, ok := run.Input["scope_prefix"].(string); ok {
		input.ScopePrefix = scopePrefix
	} else if prefix, ok := run.Input["prefix"].(string); ok {
		input.ScopePrefix = prefix
	}

	return input, nil
}

func ObjectScopeParams(bucketID, bucketPrefix string, input ScanBucketInput) storage.ObjectScopeParams {
	return storage.ObjectScopeParams{
		BucketID: bucketID,
		Prefix:   syncbucket.EffectiveListPrefix(bucketPrefix, input.ScopePrefix),
	}
}

func BucketID(run storage.JobRun) (string, error) {
	if bucketID, ok := run.Input["bucket_id"].(string); ok && bucketID != "" {
		return bucketID, nil
	}
	if run.TargetType == "bucket" && run.TargetID != "" {
		return run.TargetID, nil
	}

	return "", fmt.Errorf("scan_bucket job %q is missing bucket_id", run.ID)
}
