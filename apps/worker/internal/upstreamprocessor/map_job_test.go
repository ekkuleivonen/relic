package upstreamprocessor

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestJobTypeForEventNameImportEvents(t *testing.T) {
	for _, eventName := range []string{
		"ObjectCreated:Put",
		"ObjectCreated:Post",
		"ObjectCreated:Copy",
		"ObjectCreated:CompleteMultipartUpload",
		"s3:ObjectCreated:Put",
	} {
		jobType, ok := JobTypeForEventName(eventName)
		if !ok {
			t.Fatalf("JobTypeForEventName(%q) ok = false, want true", eventName)
		}
		if jobType != storage.JobTypeImportObjects {
			t.Fatalf("JobTypeForEventName(%q) = %q, want import_objects", eventName, jobType)
		}
	}
}

func TestJobTypeForEventNameRemoveEvents(t *testing.T) {
	for _, eventName := range []string{
		"ObjectRemoved:Delete",
		"ObjectRemoved:DeleteMarkerCreated",
		"s3:ObjectRemoved:Delete",
	} {
		jobType, ok := JobTypeForEventName(eventName)
		if !ok {
			t.Fatalf("JobTypeForEventName(%q) ok = false, want true", eventName)
		}
		if jobType != storage.JobTypeRemoveObjects {
			t.Fatalf("JobTypeForEventName(%q) = %q, want remove_objects", eventName, jobType)
		}
	}
}

func TestJobTypeForEventNameRefreshEvents(t *testing.T) {
	for _, eventName := range []string{
		"ObjectTagging:Put",
		"ObjectTagging:Delete",
		"ObjectAcl:Put",
	} {
		jobType, ok := JobTypeForEventName(eventName)
		if !ok {
			t.Fatalf("JobTypeForEventName(%q) ok = false, want true", eventName)
		}
		if jobType != storage.JobTypeRefreshObjects {
			t.Fatalf("JobTypeForEventName(%q) = %q, want refresh_objects", eventName, jobType)
		}
	}
}

func TestJobTypeForEventNameUnknown(t *testing.T) {
	if _, ok := JobTypeForEventName("s3:TestEvent"); ok {
		t.Fatal("JobTypeForEventName() ok = true, want false for unknown event")
	}
}
