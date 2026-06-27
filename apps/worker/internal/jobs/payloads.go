package jobs

import (
	"encoding/json"
	"fmt"

	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

type ObjectEvidence struct {
	ID           string `json:"id,omitempty"`
	Key          string `json:"key"`
	VersionID    string `json:"version_id,omitempty"`
	ETag         string `json:"etag,omitempty"`
	Size         int64  `json:"size,omitempty"`
	LastModified string `json:"last_modified,omitempty"`
	StorageClass string `json:"storage_class,omitempty"`
}

type ObjectMutationInput struct {
	BucketID       string           `json:"bucket_id"`
	Objects        []ObjectEvidence `json:"objects"`
	SourceJobRunID string           `json:"source_job_run_id,omitempty"`
}

func PayloadFrom(value any) (storage.JobRunPayload, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("encode job payload: %w", err)
	}

	var payload storage.JobRunPayload
	if err := json.Unmarshal(encoded, &payload); err != nil {
		return nil, fmt.Errorf("decode job payload: %w", err)
	}
	if payload == nil {
		payload = storage.JobRunPayload{}
	}

	return payload, nil
}

func DecodePayload(payload storage.JobRunPayload, target any) error {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode job payload: %w", err)
	}
	if err := json.Unmarshal(encoded, target); err != nil {
		return fmt.Errorf("decode job payload: %w", err)
	}

	return nil
}

func AttributesWithEvidence(attributes storage.ObjectAttributes, evidence ObjectEvidence) storage.ObjectAttributes {
	merged := cloneObjectAttributes(attributes)
	upstream := upstreamAttributes(merged)
	if evidence.ETag != "" {
		upstream["etag"] = evidence.ETag
	}
	if evidence.Size > 0 {
		upstream["size"] = evidence.Size
	}
	if evidence.LastModified != "" {
		upstream["last_modified"] = evidence.LastModified
	}
	s3compat.SetS3StorageClass(upstream, evidence.StorageClass)
	merged["upstream"] = upstream

	return merged
}

func cloneObjectAttributes(attributes storage.ObjectAttributes) storage.ObjectAttributes {
	if attributes == nil {
		return storage.ObjectAttributes{}
	}

	encoded, err := json.Marshal(attributes)
	if err != nil {
		return storage.ObjectAttributes{}
	}
	var cloned storage.ObjectAttributes
	if err := json.Unmarshal(encoded, &cloned); err != nil {
		return storage.ObjectAttributes{}
	}
	if cloned == nil {
		return storage.ObjectAttributes{}
	}

	return cloned
}

func upstreamAttributes(attributes storage.ObjectAttributes) map[string]any {
	upstream, ok := attributes["upstream"].(map[string]any)
	if !ok || upstream == nil {
		return map[string]any{}
	}

	return upstream
}
