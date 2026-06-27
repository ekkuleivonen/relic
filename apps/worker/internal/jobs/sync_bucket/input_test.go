package sync_bucket

import (
	"fmt"
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/verification"
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

func TestParseSyncBucketInputMinimal(t *testing.T) {
	input, err := ParseSyncBucketInput(storage.JobRun{
		TargetType: "bucket",
		TargetID:   "bucket_abc",
		Input:      storage.JobRunPayload{},
	})
	if err != nil {
		t.Fatalf("ParseSyncBucketInput returned error: %v", err)
	}
	if input.BucketID != "bucket_abc" {
		t.Fatalf("BucketID = %q, want bucket_abc", input.BucketID)
	}
	if input.ScopePrefix != "" {
		t.Fatalf("ScopePrefix = %q, want empty", input.ScopePrefix)
	}
	if input.Partition != nil {
		t.Fatalf("Partition = %#v, want nil", input.Partition)
	}
}

func TestParseSyncBucketInputWithScopePrefix(t *testing.T) {
	input, err := ParseSyncBucketInput(storage.JobRun{
		Input: storage.JobRunPayload{
			"bucket_id":    "bucket_abc",
			"scope_prefix": "batch/",
		},
	})
	if err != nil {
		t.Fatalf("ParseSyncBucketInput returned error: %v", err)
	}
	if input.ScopePrefix != "batch/" {
		t.Fatalf("ScopePrefix = %q, want batch/", input.ScopePrefix)
	}
}

func TestParseSyncBucketInputAcceptsLegacyPrefixField(t *testing.T) {
	input, err := ParseSyncBucketInput(storage.JobRun{
		Input: storage.JobRunPayload{
			"bucket_id": "bucket_abc",
			"prefix":    "batch/",
		},
	})
	if err != nil {
		t.Fatalf("ParseSyncBucketInput returned error: %v", err)
	}
	if input.ScopePrefix != "batch/" {
		t.Fatalf("ScopePrefix = %q, want batch/", input.ScopePrefix)
	}
}

func TestParseSyncBucketInputPrefersScopePrefixOverPrefix(t *testing.T) {
	input, err := ParseSyncBucketInput(storage.JobRun{
		Input: storage.JobRunPayload{
			"bucket_id":    "bucket_abc",
			"scope_prefix": "scope/",
			"prefix":       "legacy/",
		},
	})
	if err != nil {
		t.Fatalf("ParseSyncBucketInput returned error: %v", err)
	}
	if input.ScopePrefix != "scope/" {
		t.Fatalf("ScopePrefix = %q, want scope/", input.ScopePrefix)
	}
}

func TestParseSyncBucketInputWithPartition(t *testing.T) {
	input, err := ParseSyncBucketInput(storage.JobRun{
		Input: storage.JobRunPayload{
			"bucket_id": "bucket_abc",
			"partition": map[string]any{
				"scheme":  "hash",
				"modulus": float64(256),
				"index":   float64(42),
			},
		},
	})
	if err != nil {
		t.Fatalf("ParseSyncBucketInput returned error: %v", err)
	}
	if input.Partition == nil {
		t.Fatal("Partition = nil, want hash partition")
	}
	if input.Partition.Index != 42 {
		t.Fatalf("Partition.Index = %d, want 42", input.Partition.Index)
	}
	if input.Partition.Modulus != 256 {
		t.Fatalf("Partition.Modulus = %d, want 256", input.Partition.Modulus)
	}
	if input.Partition.Scheme != verification.SchemeHash {
		t.Fatalf("Partition.Scheme = %q, want %q", input.Partition.Scheme, verification.SchemeHash)
	}
}

func TestParseSyncBucketInputRejectsInvalidPartition(t *testing.T) {
	tests := []struct {
		name  string
		input storage.JobRunPayload
	}{
		{
			name: "missing scheme",
			input: storage.JobRunPayload{
				"bucket_id": "bucket_abc",
				"partition": map[string]any{
					"modulus": float64(256),
					"index":   float64(42),
				},
			},
		},
		{
			name: "unsupported scheme",
			input: storage.JobRunPayload{
				"bucket_id": "bucket_abc",
				"partition": map[string]any{
					"scheme":  "prefix",
					"modulus": float64(256),
					"index":   float64(42),
				},
			},
		},
		{
			name: "index out of range",
			input: storage.JobRunPayload{
				"bucket_id": "bucket_abc",
				"partition": map[string]any{
					"scheme":  "hash",
					"modulus": float64(256),
					"index":   float64(256),
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := ParseSyncBucketInput(storage.JobRun{Input: tt.input}); err == nil {
				t.Fatalf("ParseSyncBucketInput returned nil error for %#v", tt.input)
			}
		})
	}
}

func TestEffectiveListPrefixJoinsBucketAndScope(t *testing.T) {
	tests := []struct {
		name         string
		bucketPrefix string
		scopePrefix  string
		want         string
	}{
		{name: "bucket only", bucketPrefix: "raw/", scopePrefix: "", want: "raw/"},
		{name: "scope only", bucketPrefix: "", scopePrefix: "batch/", want: "batch/"},
		{name: "joined", bucketPrefix: "raw/", scopePrefix: "batch/", want: "raw/batch/"},
		{name: "both empty", bucketPrefix: "", scopePrefix: "", want: ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := EffectiveListPrefix(tt.bucketPrefix, tt.scopePrefix)
			if got != tt.want {
				t.Fatalf("EffectiveListPrefix() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestKeyMatchesPartition(t *testing.T) {
	partition := verification.PartitionFromIndex(42, verification.DefaultModulus)
	key := keyForPartition(t, partition.Index, partition.Modulus)

	if !KeyMatchesPartition(key, partition) {
		t.Fatalf("KeyMatchesPartition(%q, %v) = false, want true", key, partition)
	}
	if KeyMatchesPartition(keyForPartition(t, 99, partition.Modulus), partition) {
		t.Fatalf("KeyMatchesPartition for other partition = true, want false")
	}
}

func keyForPartition(t *testing.T, index, modulus uint32) string {
	t.Helper()

	for i := range 10_000 {
		key := fmt.Sprintf("objects/%d.dat", i)
		if verification.PartitionIndex(key, modulus) == index {
			return key
		}
	}

	t.Fatalf("could not find key for partition %d/%d", index, modulus)
	return ""
}
