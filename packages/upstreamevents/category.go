package upstreamevents

import "strings"

const (
	EventCategoryCreated          = "created"
	EventCategoryRemoved          = "removed"
	EventCategoryMetadataChanged  = "metadata_changed"
	EventCategoryOther            = "other"
)

func EventCategory(eventName string) string {
	switch {
	case strings.HasPrefix(eventName, "ObjectCreated:"),
		strings.HasPrefix(eventName, "s3:ObjectCreated:"):
		return EventCategoryCreated
	case strings.HasPrefix(eventName, "ObjectRemoved:"),
		strings.HasPrefix(eventName, "s3:ObjectRemoved:"):
		return EventCategoryRemoved
	case strings.Contains(eventName, "Tagging"),
		strings.HasPrefix(eventName, "ObjectAcl:"):
		return EventCategoryMetadataChanged
	default:
		return EventCategoryOther
	}
}

func BucketEventStatsSeries() []string {
	return []string{
		EventCategoryCreated,
		EventCategoryRemoved,
		EventCategoryMetadataChanged,
		EventCategoryOther,
	}
}
