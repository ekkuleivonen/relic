package detect_duplicates

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestOriginalObjectUsesOldestUpstreamLastModified(t *testing.T) {
	objects := []storage.Object{
		{
			ID: "object_newer",
			Attributes: storage.ObjectAttributes{
				"upstream": map[string]any{
					"last_modified": "2026-06-02T00:00:00Z",
				},
			},
		},
		{
			ID: "object_older",
			Attributes: storage.ObjectAttributes{
				"upstream": map[string]any{
					"last_modified": "2026-06-01T00:00:00Z",
				},
			},
		},
	}

	original := originalObject(objects)
	if original.ID != "object_older" {
		t.Fatalf("original ID = %q, want object_older", original.ID)
	}
}

func TestOriginalObjectBreaksTiesByObjectID(t *testing.T) {
	objects := []storage.Object{
		{
			ID: "object_b",
			Attributes: storage.ObjectAttributes{
				"upstream": map[string]any{
					"last_modified": "2026-06-01T00:00:00Z",
				},
			},
		},
		{
			ID: "object_a",
			Attributes: storage.ObjectAttributes{
				"upstream": map[string]any{
					"last_modified": "2026-06-01T00:00:00Z",
				},
			},
		},
	}

	original := originalObject(objects)
	if original.ID != "object_a" {
		t.Fatalf("original ID = %q, want object_a", original.ID)
	}
}

func TestCachedContentSHA256RequiresMatchingEvidence(t *testing.T) {
	object := storage.Object{
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag": "\"abc\"",
				"size": int64(10),
			},
			"extracted": map[string]any{
				"content_sha256": "deadbeef",
			},
		},
	}

	hash, ok := cachedContentSHA256(object, "\"abc\"", 10)
	if !ok || hash != "deadbeef" {
		t.Fatalf("cached hash = %q, ok = %v, want deadbeef true", hash, ok)
	}

	if _, ok := cachedContentSHA256(object, "\"def\"", 10); ok {
		t.Fatal("expected cache miss for mismatched etag")
	}
}
