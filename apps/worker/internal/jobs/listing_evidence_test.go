package jobs

import (
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

func TestObjectEvidenceFromListedObject(t *testing.T) {
	listedAt := time.Date(2026, 6, 1, 12, 0, 0, 0, time.FixedZone("EST", -5*3600))

	evidence := ObjectEvidenceFromListedObject(s3compat.ListedObject{
		Key:          "photos/a.jpg",
		ETag:         "\"abc123\"",
		Size:         123,
		LastModified: listedAt,
		StorageClass: "STANDARD",
	})

	if evidence.Key != "photos/a.jpg" {
		t.Fatalf("Key = %q, want photos/a.jpg", evidence.Key)
	}
	if evidence.ETag != "\"abc123\"" {
		t.Fatalf("ETag = %q, want \"abc123\"", evidence.ETag)
	}
	if evidence.Size != 123 {
		t.Fatalf("Size = %d, want 123", evidence.Size)
	}
	if evidence.LastModified != "2026-06-01T17:00:00Z" {
		t.Fatalf("LastModified = %q, want UTC RFC3339", evidence.LastModified)
	}
	if evidence.StorageClass != "STANDARD" {
		t.Fatalf("StorageClass = %q, want STANDARD", evidence.StorageClass)
	}
}

func TestListingEvidenceFromListedObject(t *testing.T) {
	listedAt := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)

	evidence := ListingEvidenceFromListedObject(s3compat.ListedObject{
		Key:          "photos/a.jpg",
		ETag:         "\"abc123\"",
		Size:         456,
		LastModified: listedAt,
		StorageClass: "GLACIER",
	})

	if evidence.Size != 456 {
		t.Fatalf("Size = %d, want 456", evidence.Size)
	}
	if evidence.ETag != "\"abc123\"" {
		t.Fatalf("ETag = %q, want \"abc123\"", evidence.ETag)
	}
	if evidence.LastModified != "2026-06-01T00:00:00Z" {
		t.Fatalf("LastModified = %q, want 2026-06-01T00:00:00Z", evidence.LastModified)
	}
	if evidence.StorageClass != "GLACIER" {
		t.Fatalf("StorageClass = %q, want GLACIER", evidence.StorageClass)
	}
}

func TestListingEvidenceFromLocalObject(t *testing.T) {
	object := storage.Object{
		Key: "photos/a.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"abc123\"",
				"size":          float64(789),
				"last_modified": "2026-06-01T00:00:00Z",
				"s3": map[string]any{
					"storage_class": "STANDARD",
				},
			},
		},
	}

	evidence := ListingEvidenceFromLocalObject(object)

	if evidence.Size != 789 {
		t.Fatalf("Size = %d, want 789", evidence.Size)
	}
	if evidence.ETag != "\"abc123\"" {
		t.Fatalf("ETag = %q, want \"abc123\"", evidence.ETag)
	}
	if evidence.LastModified != "2026-06-01T00:00:00Z" {
		t.Fatalf("LastModified = %q, want 2026-06-01T00:00:00Z", evidence.LastModified)
	}
	if evidence.StorageClass != "STANDARD" {
		t.Fatalf("StorageClass = %q, want STANDARD", evidence.StorageClass)
	}
}

func TestListingEvidenceFromLocalObjectMissingUpstream(t *testing.T) {
	evidence := ListingEvidenceFromLocalObject(storage.Object{Key: "photos/a.jpg"})

	if evidence.Size != 0 || evidence.ETag != "" || evidence.LastModified != "" || evidence.StorageClass != "" {
		t.Fatalf("ListingEvidenceFromLocalObject() = %#v, want zero evidence", evidence)
	}
}

func TestObjectChangedReturnsTrueWhenUpstreamAttributesMissing(t *testing.T) {
	changed := ObjectChanged(
		s3compat.ListedObject{Key: "photos/a.jpg", ETag: "\"abc\"", Size: 1, LastModified: time.Unix(0, 0).UTC()},
		storage.Object{Key: "photos/a.jpg"},
	)
	if !changed {
		t.Fatal("ObjectChanged returned false, want true when upstream attributes are missing")
	}
}

func TestObjectChangedDetectsFieldDrift(t *testing.T) {
	listedAt := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	localObject := storage.Object{
		Key: "photos/a.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"abc123\"",
				"size":          int64(123),
				"last_modified": "2026-06-01T00:00:00Z",
				"s3": map[string]any{
					"storage_class": "STANDARD",
				},
			},
		},
	}
	baseUpstream := s3compat.ListedObject{
		Key:          "photos/a.jpg",
		ETag:         "\"abc123\"",
		Size:         123,
		LastModified: listedAt,
		StorageClass: "STANDARD",
	}

	tests := []struct {
		name     string
		upstream s3compat.ListedObject
		want     bool
	}{
		{
			name:     "unchanged",
			upstream: baseUpstream,
			want:     false,
		},
		{
			name:     "etag",
			upstream: s3compat.ListedObject{Key: baseUpstream.Key, ETag: "\"changed\"", Size: baseUpstream.Size, LastModified: baseUpstream.LastModified, StorageClass: baseUpstream.StorageClass},
			want:     true,
		},
		{
			name:     "size",
			upstream: s3compat.ListedObject{Key: baseUpstream.Key, ETag: baseUpstream.ETag, Size: 999, LastModified: baseUpstream.LastModified, StorageClass: baseUpstream.StorageClass},
			want:     true,
		},
		{
			name:     "last_modified",
			upstream: s3compat.ListedObject{Key: baseUpstream.Key, ETag: baseUpstream.ETag, Size: baseUpstream.Size, LastModified: listedAt.Add(time.Hour), StorageClass: baseUpstream.StorageClass},
			want:     true,
		},
		{
			name:     "storage_class",
			upstream: s3compat.ListedObject{Key: baseUpstream.Key, ETag: baseUpstream.ETag, Size: baseUpstream.Size, LastModified: baseUpstream.LastModified, StorageClass: "GLACIER"},
			want:     true,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := ObjectChanged(test.upstream, localObject); got != test.want {
				t.Fatalf("ObjectChanged() = %v, want %v", got, test.want)
			}
		})
	}
}

func TestObjectChangedReadsNestedStorageClass(t *testing.T) {
	listedAt := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	localObject := storage.Object{
		Key: "photos/a.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{
				"etag":          "\"abc123\"",
				"size":          int64(123),
				"last_modified": "2026-06-01T00:00:00Z",
				"s3": map[string]any{
					"storage_class": "STANDARD",
				},
			},
		},
	}
	upstream := s3compat.ListedObject{
		Key:          "photos/a.jpg",
		ETag:         "\"abc123\"",
		Size:         123,
		LastModified: listedAt,
		StorageClass: "STANDARD",
	}

	if ObjectChanged(upstream, localObject) {
		t.Fatal("ObjectChanged returned true, want false for nested storage_class match")
	}
}

func TestPlanObjectMutations(t *testing.T) {
	listedAt := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	upstreamObjects := map[string]s3compat.ListedObject{
		"photos/new.jpg": {
			Key:          "photos/new.jpg",
			ETag:         "\"new\"",
			Size:         10,
			LastModified: listedAt,
			StorageClass: "STANDARD",
		},
		"photos/changed.jpg": {
			Key:          "photos/changed.jpg",
			ETag:         "\"changed\"",
			Size:         20,
			LastModified: listedAt,
			StorageClass: "STANDARD",
		},
		"photos/same.jpg": {
			Key:          "photos/same.jpg",
			ETag:         "\"same\"",
			Size:         30,
			LastModified: listedAt,
			StorageClass: "STANDARD",
		},
	}
	localObjects := []storage.Object{
		{
			ID:  "object_changed",
			Key: "photos/changed.jpg",
			Attributes: storage.ObjectAttributes{
				"upstream": map[string]any{
					"etag":          "\"old\"",
					"size":          int64(20),
					"last_modified": "2026-06-01T00:00:00Z",
					"s3": map[string]any{
						"storage_class": "STANDARD",
					},
				},
			},
		},
		{
			ID:  "object_same",
			Key: "photos/same.jpg",
			Attributes: storage.ObjectAttributes{
				"upstream": map[string]any{
					"etag":          "\"same\"",
					"size":          int64(30),
					"last_modified": "2026-06-01T00:00:00Z",
					"s3": map[string]any{
						"storage_class": "STANDARD",
					},
				},
			},
		},
		{
			ID:  "object_remove",
			Key: "photos/remove.jpg",
		},
	}

	importObjects, refreshObjects, removeObjects := PlanObjectMutations(upstreamObjects, localObjects)

	if len(importObjects) != 1 || importObjects[0].Key != "photos/new.jpg" {
		t.Fatalf("importObjects = %#v, want single photos/new.jpg import", importObjects)
	}
	if len(refreshObjects) != 1 || refreshObjects[0].ID != "object_changed" || refreshObjects[0].Key != "photos/changed.jpg" {
		t.Fatalf("refreshObjects = %#v, want single changed object refresh", refreshObjects)
	}
	if len(removeObjects) != 1 || removeObjects[0].ID != "object_remove" || removeObjects[0].Key != "photos/remove.jpg" {
		t.Fatalf("removeObjects = %#v, want single remove object", removeObjects)
	}
}
