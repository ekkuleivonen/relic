package upstreamprocessor

import (
	"strings"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func JobTypeForEventName(eventName string) (storage.JobType, bool) {
	switch {
	case strings.HasPrefix(eventName, "ObjectCreated:"),
		strings.HasPrefix(eventName, "s3:ObjectCreated:"):
		return storage.JobTypeImportObjects, true
	case strings.HasPrefix(eventName, "ObjectRemoved:"),
		strings.HasPrefix(eventName, "s3:ObjectRemoved:"):
		return storage.JobTypeRemoveObjects, true
	case strings.Contains(eventName, "Tagging"),
		strings.HasPrefix(eventName, "ObjectAcl:"):
		return storage.JobTypeRefreshObjects, true
	default:
		return "", false
	}
}
