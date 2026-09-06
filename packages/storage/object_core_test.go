package storage

import (
	"testing"
	"time"
)

func TestAttributeValueHandlesTypedRootAndNestedMaps(t *testing.T) {
	attrs := ObjectAttributes{"user": map[string]any{"review": map[string]any{"status": "approved"}}}
	value, ok := attributeValue(attrs, "user.review.status")
	if !ok || value != "approved" {
		t.Fatalf("value=%v found=%v", value, ok)
	}
}

func TestCoreTimestampPreservesSubsecondPrecision(t *testing.T) {
	at := time.Date(2026, 9, 6, 1, 2, 3, 123456789, time.UTC)
	attrs := ObjectAttributes{}
	injectCoreAttributes(attrs, "object-test", at)
	first, last, err := coreTimestamps(attrs)
	if err != nil {
		t.Fatal(err)
	}
	if !first.Equal(at) || !last.Equal(at) {
		t.Fatalf("precision lost: %v / %v", first, last)
	}
}
