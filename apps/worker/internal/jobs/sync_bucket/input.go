package sync_bucket

import (
	"fmt"
	"strings"

	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/verification"
)

type SyncBucketInput struct {
	BucketID       string
	ScopePrefix    string
	Partition      *verification.Partition
	SourceJobRunID string
}

func ParseSyncBucketInput(run storage.JobRun) (SyncBucketInput, error) {
	bucketID, err := BucketID(run)
	if err != nil {
		return SyncBucketInput{}, err
	}

	input := SyncBucketInput{
		BucketID: bucketID,
	}
	if scopePrefix, ok := run.Input["scope_prefix"].(string); ok {
		input.ScopePrefix = scopePrefix
	} else if prefix, ok := run.Input["prefix"].(string); ok {
		input.ScopePrefix = prefix
	}
	if sourceJobRunID, ok := run.Input["source_job_run_id"].(string); ok {
		input.SourceJobRunID = sourceJobRunID
	}
	if partitionValue, ok := run.Input["partition"]; ok {
		partition, err := parsePartitionFromPayload(partitionValue)
		if err != nil {
			return SyncBucketInput{}, err
		}
		input.Partition = partition
	}

	return input, nil
}

func EffectiveListPrefix(bucketPrefix, scopePrefix string) string {
	if scopePrefix == "" {
		return bucketPrefix
	}
	if bucketPrefix == "" {
		return scopePrefix
	}

	return strings.TrimSuffix(bucketPrefix, "/") + "/" + strings.TrimPrefix(scopePrefix, "/")
}

func ObjectScopeParams(bucketID, bucketPrefix string, input SyncBucketInput) storage.ObjectScopeParams {
	return storage.ObjectScopeParams{
		BucketID: bucketID,
		Prefix:   EffectiveListPrefix(bucketPrefix, input.ScopePrefix),
	}
}

func KeyMatchesPartition(key string, partition verification.Partition) bool {
	return verification.PartitionIndex(key, partition.Modulus) == partition.Index
}

func parsePartitionFromPayload(value any) (*verification.Partition, error) {
	fields, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("parse partition: expected object")
	}

	scheme, _ := fields["scheme"].(string)
	if scheme != verification.SchemeHash {
		return nil, fmt.Errorf("parse partition: unsupported scheme %q", scheme)
	}

	modulus, err := uint32FromPayload(fields["modulus"])
	if err != nil {
		return nil, fmt.Errorf("parse partition: invalid modulus: %w", err)
	}
	if modulus == 0 {
		return nil, fmt.Errorf("parse partition: modulus must be greater than zero")
	}

	index, err := uint32FromPayload(fields["index"])
	if err != nil {
		return nil, fmt.Errorf("parse partition: invalid index: %w", err)
	}
	if index >= modulus {
		return nil, fmt.Errorf("parse partition: index %d out of range for modulus %d", index, modulus)
	}

	partition := verification.PartitionFromIndex(index, modulus)
	return &partition, nil
}

func uint32FromPayload(value any) (uint32, error) {
	switch typed := value.(type) {
	case float64:
		if typed < 0 || typed > float64(^uint32(0)) {
			return 0, fmt.Errorf("value %v out of uint32 range", typed)
		}
		return uint32(typed), nil
	case int:
		if typed < 0 {
			return 0, fmt.Errorf("value %d out of uint32 range", typed)
		}
		return uint32(typed), nil
	case int64:
		if typed < 0 || typed > int64(^uint32(0)) {
			return 0, fmt.Errorf("value %d out of uint32 range", typed)
		}
		return uint32(typed), nil
	case uint32:
		return typed, nil
	default:
		return 0, fmt.Errorf("unsupported type %T", value)
	}
}
