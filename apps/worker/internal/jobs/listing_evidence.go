package jobs

import (
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

type ListingEvidence struct {
	Size         int64
	ETag         string
	LastModified string
	StorageClass string
}

func ObjectEvidenceFromListedObject(object s3compat.ListedObject) ObjectEvidence {
	return ObjectEvidence{
		Key:          object.Key,
		ETag:         object.ETag,
		Size:         object.Size,
		LastModified: object.LastModified.UTC().Format(time.RFC3339),
		StorageClass: object.StorageClass,
	}
}

func ListingEvidenceFromListedObject(object s3compat.ListedObject) ListingEvidence {
	return ListingEvidence{
		Size:         object.Size,
		ETag:         object.ETag,
		LastModified: object.LastModified.UTC().Format(time.RFC3339),
		StorageClass: object.StorageClass,
	}
}

func ListingEvidenceFromLocalObject(object storage.Object) ListingEvidence {
	upstreamAttributes, _ := object.Attributes["upstream"].(map[string]any)
	if upstreamAttributes == nil {
		return ListingEvidence{}
	}

	return ListingEvidence{
		Size:         int64Attribute(upstreamAttributes["size"]),
		ETag:         stringAttribute(upstreamAttributes["etag"]),
		LastModified: stringAttribute(upstreamAttributes["last_modified"]),
		StorageClass: storageClassAttribute(upstreamAttributes),
	}
}

func PlanObjectMutations(upstreamObjects map[string]s3compat.ListedObject, localObjects []storage.Object) ([]ObjectEvidence, []ObjectEvidence, []ObjectEvidence) {
	localByKey := map[string]storage.Object{}
	for _, object := range localObjects {
		localByKey[object.Key] = object
	}

	importObjects := []ObjectEvidence{}
	refreshObjects := []ObjectEvidence{}
	for key, upstreamObject := range upstreamObjects {
		evidence := ObjectEvidenceFromListedObject(upstreamObject)
		localObject, exists := localByKey[key]
		if !exists {
			importObjects = append(importObjects, evidence)
			continue
		}
		evidence.ID = localObject.ID
		if ObjectChanged(upstreamObject, localObject) {
			refreshObjects = append(refreshObjects, evidence)
		}
	}

	removeObjects := []ObjectEvidence{}
	for key, localObject := range localByKey {
		if _, exists := upstreamObjects[key]; exists {
			continue
		}
		removeObjects = append(removeObjects, ObjectEvidence{
			ID:  localObject.ID,
			Key: localObject.Key,
		})
	}

	return importObjects, refreshObjects, removeObjects
}

func ObjectChanged(upstreamObject s3compat.ListedObject, localObject storage.Object) bool {
	upstreamAttributes, _ := localObject.Attributes["upstream"].(map[string]any)
	if upstreamAttributes == nil {
		return true
	}

	return upstreamAttributes["etag"] != upstreamObject.ETag ||
		int64Attribute(upstreamAttributes["size"]) != upstreamObject.Size ||
		upstreamAttributes["last_modified"] != upstreamObject.LastModified.UTC().Format(time.RFC3339) ||
		storageClassAttribute(upstreamAttributes) != upstreamObject.StorageClass
}

func int64Attribute(value any) int64 {
	switch typed := value.(type) {
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

func stringAttribute(value any) string {
	if typed, ok := value.(string); ok {
		return typed
	}

	return ""
}

func storageClassAttribute(upstreamAttributes map[string]any) string {
	if value, ok := upstreamAttributes["storage_class"].(string); ok {
		return value
	}
	for _, namespace := range []string{"s3", "gcp"} {
		nested, ok := upstreamAttributes[namespace].(map[string]any)
		if !ok {
			continue
		}
		if value, ok := nested["storage_class"].(string); ok {
			return value
		}
	}

	return ""
}
