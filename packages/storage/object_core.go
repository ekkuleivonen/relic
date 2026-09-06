package storage

import (
	"encoding/json"
	"fmt"
	"time"
)

const (
	CoreNamespace           = "core"
	CoreObjectIDPath        = "core.object_id"
	CoreFirstSeenAtPath     = "core.first_seen_at"
	CoreLastSeenAtPath      = "core.last_seen_at"
	UpstreamS3VersionIDPath = "upstream.s3.version_id"
)

func injectCoreAttributes(attributes ObjectAttributes, objectID string, seenAt time.Time) {
	if attributes == nil {
		return
	}

	core, ok := attributes[CoreNamespace].(map[string]any)
	if !ok {
		core = map[string]any{}
	}

	core["object_id"] = objectID
	core["last_seen_at"] = seenAt.UTC().Format(time.RFC3339Nano)
	if _, exists := core["first_seen_at"]; !exists {
		core["first_seen_at"] = seenAt.UTC().Format(time.RFC3339Nano)
	}

	attributes[CoreNamespace] = core
}

func coreTimestamps(attributes ObjectAttributes) (time.Time, time.Time, error) {
	core, ok := attributes[CoreNamespace].(map[string]any)
	if !ok {
		return time.Time{}, time.Time{}, nil
	}

	firstSeen, err := parseCoreTimestamp(core["first_seen_at"])
	if err != nil {
		return time.Time{}, time.Time{}, fmt.Errorf("parse core.first_seen_at: %w", err)
	}
	lastSeen, err := parseCoreTimestamp(core["last_seen_at"])
	if err != nil {
		return time.Time{}, time.Time{}, fmt.Errorf("parse core.last_seen_at: %w", err)
	}

	return firstSeen, lastSeen, nil
}

func parseCoreTimestamp(value any) (time.Time, error) {
	if value == nil {
		return time.Time{}, nil
	}

	text, ok := value.(string)
	if !ok || text == "" {
		return time.Time{}, nil
	}

	parsed, err := time.Parse(time.RFC3339, text)
	if err != nil {
		return time.Time{}, err
	}

	return parsed.UTC(), nil
}

func attributeString(attributes ObjectAttributes, path string) string {
	value, ok := attributeValue(attributes, path)
	if !ok {
		return ""
	}

	text, ok := value.(string)
	if !ok {
		return ""
	}

	return text
}

func attributeValue(attributes ObjectAttributes, path string) (any, bool) {
	if attributes == nil {
		return nil, false
	}

	parts, err := NewJSONBPath(splitAttributePath(path)...)
	if err != nil {
		return nil, false
	}

	current := any(attributes)
	for _, part := range parts {
		asMap, ok := asNestedAttributeMap(current)
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

func cloneObjectAttributes(attributes ObjectAttributes) ObjectAttributes {
	if attributes == nil {
		return ObjectAttributes{}
	}

	encoded, err := json.Marshal(attributes)
	if err != nil {
		return ObjectAttributes{}
	}

	cloned := ObjectAttributes{}
	if err := json.Unmarshal(encoded, &cloned); err != nil {
		return ObjectAttributes{}
	}
	if cloned == nil {
		return ObjectAttributes{}
	}

	return cloned
}
