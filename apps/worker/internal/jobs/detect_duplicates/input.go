package detect_duplicates

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/elei-io/pithosys/packages/storage"
)

const (
	extractedContentSHA256Path = "extracted.content_sha256"
	upstreamLastModifiedPath   = "upstream.last_modified"
)

type ScopeInput struct {
	BucketIDs []string `json:"bucket_ids"`
	Prefixes  []string `json:"prefixes"`
}

type Input struct {
	Scope ScopeInput `json:"scope"`
}

func ParseInput(run storage.JobRun) (Input, error) {
	if run.Input == nil {
		return Input{}, nil
	}

	encoded, err := json.Marshal(run.Input)
	if err != nil {
		return Input{}, fmt.Errorf("detect_duplicates job %q: encode input: %w", run.ID, err)
	}

	var input Input
	if err := json.Unmarshal(encoded, &input); err != nil {
		return Input{}, fmt.Errorf("detect_duplicates job %q: decode input: %w", run.ID, err)
	}

	return input, nil
}

func ScopeFromInput(input Input) storage.DuplicateDetectScope {
	return storage.DuplicateDetectScope{
		BucketIDs: input.Scope.BucketIDs,
		Prefixes:  input.Scope.Prefixes,
	}
}

func originalObject(objects []storage.Object) storage.Object {
	if len(objects) == 0 {
		return storage.Object{}
	}

	original := objects[0]
	originalTime := upstreamLastModified(original)

	for _, object := range objects[1:] {
		candidateTime := upstreamLastModified(object)
		switch {
		case candidateTime.Before(originalTime):
			original = object
			originalTime = candidateTime
		case candidateTime.Equal(originalTime) && object.ID < original.ID:
			original = object
		}
	}

	return original
}

func upstreamLastModified(object storage.Object) time.Time {
	value, ok := attributeValue(object.Attributes, upstreamLastModifiedPath)
	if !ok {
		return time.Time{}
	}

	text, ok := value.(string)
	if !ok || text == "" {
		return time.Time{}
	}

	parsed, err := time.Parse(time.RFC3339, text)
	if err != nil {
		return time.Time{}
	}

	return parsed.UTC()
}

func cachedContentSHA256(object storage.Object, etag string, size int64) (string, bool) {
	if etag == "" || size <= 0 {
		return "", false
	}
	if listingEvidenceETag(object) != etag || listingEvidenceSize(object) != size {
		return "", false
	}

	value, ok := attributeValue(object.Attributes, extractedContentSHA256Path)
	if !ok {
		return "", false
	}
	hash, ok := value.(string)
	if !ok || hash == "" {
		return "", false
	}

	return hash, true
}

func listingEvidenceETag(object storage.Object) string {
	upstream, ok := object.Attributes["upstream"].(map[string]any)
	if !ok || upstream == nil {
		return ""
	}
	text, ok := upstream["etag"].(string)
	if !ok {
		return ""
	}

	return text
}

func listingEvidenceSize(object storage.Object) int64 {
	upstream, ok := object.Attributes["upstream"].(map[string]any)
	if !ok || upstream == nil {
		return 0
	}

	switch typed := upstream["size"].(type) {
	case int64:
		return typed
	case int:
		return int64(typed)
	case float64:
		return int64(typed)
	default:
		return 0
	}
}

func attributeValue(attributes storage.ObjectAttributes, path string) (any, bool) {
	if attributes == nil {
		return nil, false
	}

	parts := splitAttributePath(path)
	current := any(map[string]any(attributes))
	for _, part := range parts {
		asMap, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		next, ok := asMap[part]
		if !ok {
			return nil, false
		}
		current = next
	}

	return current, true
}

func splitAttributePath(path string) []string {
	parts := []string{}
	start := 0
	for index := 0; index < len(path); index++ {
		if path[index] != '.' {
			continue
		}
		if segment := path[start:index]; segment != "" {
			parts = append(parts, segment)
		}
		start = index + 1
	}
	if segment := path[start:]; segment != "" {
		parts = append(parts, segment)
	}

	return parts
}

func mergeExtractedContentSHA256(object storage.Object, hash string) storage.ObjectAttributes {
	attributes := cloneObjectAttributes(object.Attributes)
	extracted, ok := attributes["extracted"].(map[string]any)
	if !ok || extracted == nil {
		extracted = map[string]any{}
	}
	extracted["content_sha256"] = hash
	attributes["extracted"] = extracted

	return attributes
}

func cloneObjectAttributes(attributes storage.ObjectAttributes) storage.ObjectAttributes {
	if attributes == nil {
		return storage.ObjectAttributes{}
	}

	encoded, err := json.Marshal(attributes)
	if err != nil {
		return storage.ObjectAttributes{}
	}

	cloned := storage.ObjectAttributes{}
	if err := json.Unmarshal(encoded, &cloned); err != nil {
		return storage.ObjectAttributes{}
	}
	if cloned == nil {
		return storage.ObjectAttributes{}
	}

	return cloned
}
