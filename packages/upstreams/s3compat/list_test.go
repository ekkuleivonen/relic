package s3compat

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/storage"
)

func TestParseListObjectsV2(t *testing.T) {
	tests := []struct {
		name        string
		upstream    Upstream
		wantEntries []ListedObject
	}{
		{
			name:     "aws",
			upstream: UpstreamAWS,
			wantEntries: []ListedObject{
				{
					Key:          "photos/a.jpg",
					ETag:         "\"fba9dede5f27731c9771645a39863328\"",
					Size:         434234,
					LastModified: mustTime(t, "2026-06-26T01:00:00Z"),
					StorageClass: "STANDARD",
				},
				{
					Key:          "photos/b.jpg",
					ETag:         "\"30a6ec7e1a9ad79c203d05a589c8b400\"",
					Size:         77,
					LastModified: mustTime(t, "2026-06-26T01:01:00Z"),
					StorageClass: "STANDARD",
				},
			},
		},
		{
			name:     "r2",
			upstream: UpstreamR2,
			wantEntries: []ListedObject{
				{
					Key:          "photos/a.jpg",
					ETag:         "\"6f5902ac237024bdd0c176cb93063dc4\"",
					Size:         434234,
					LastModified: mustTime(t, "2026-06-26T01:00:00Z"),
					StorageClass: "STANDARD",
				},
				{
					Key:          "photos/b.jpg",
					ETag:         "\"2963669d5f412e03c10a077bde633b7a\"",
					Size:         77,
					LastModified: mustTime(t, "2026-06-26T01:01:00Z"),
					StorageClass: "STANDARD",
				},
			},
		},
		{
			name:     "b2",
			upstream: UpstreamB2,
			wantEntries: []ListedObject{
				{
					Key:          "photos/a.jpg",
					ETag:         "\"85f30635602dc09bd85957a6e82a2c21\"",
					Size:         434234,
					LastModified: mustTime(t, "2022-01-28T23:12:33Z"),
					StorageClass: "STANDARD",
				},
				{
					Key:          "photos/b.jpg",
					ETag:         "\"3a6eb0790f39ac87c94f3856b2dd2c5d\"",
					Size:         77,
					LastModified: mustTime(t, "2022-01-28T23:13:33Z"),
					StorageClass: "STANDARD",
				},
			},
		},
		{
			name:     "rustfs",
			upstream: UpstreamRustFS,
			wantEntries: []ListedObject{
				{
					Key:          "photos/a.jpg",
					ETag:         "\"d41d8cd98f00b204e9800998ecf8427e\"",
					Size:         434234,
					LastModified: mustTime(t, "2026-06-26T01:00:00Z"),
					StorageClass: "STANDARD",
				},
				{
					Key:          "photos/b.jpg",
					ETag:         "\"0cc175b9c0f1b6a831c399e269772661\"",
					Size:         77,
					LastModified: mustTime(t, "2026-06-26T01:01:00Z"),
					StorageClass: "STANDARD",
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			fixture := readListFixture(t, "ListObjectsV2", tt.name)

			got, err := ParseListObjectsV2(tt.upstream, fixture.Response)
			if err != nil {
				t.Fatalf("ParseListObjectsV2 returned error: %v", err)
			}

			if !reflect.DeepEqual(got.Objects, tt.wantEntries) {
				t.Fatalf("objects mismatch\n got: %#v\nwant: %#v", got.Objects, tt.wantEntries)
			}
			if got.IsTruncated {
				t.Fatal("IsTruncated = true, want false")
			}
		})
	}
}

func TestParseListObjectsV2GCPUnsupported(t *testing.T) {
	fixture := readListFixture(t, "ListObjectsV2", "gcp")

	_, err := ParseListObjectsV2(UpstreamGCP, fixture.Response)
	if err == nil {
		t.Fatal("ParseListObjectsV2 returned nil error, want GCS unsupported/error response")
	}
}

func TestParseListObjects(t *testing.T) {
	tests := []struct {
		name     string
		upstream Upstream
		wantKey  string
		wantETag string
	}{
		{name: "aws", upstream: UpstreamAWS, wantKey: "photos/a.jpg", wantETag: "\"fba9dede5f27731c9771645a39863328\""},
		{name: "r2", upstream: UpstreamR2, wantKey: "photos/a.jpg", wantETag: "\"6f5902ac237024bdd0c176cb93063dc4\""},
		{name: "b2", upstream: UpstreamB2, wantKey: "photos/a.jpg", wantETag: "\"85f30635602dc09bd85957a6e82a2c21\""},
		{name: "gcp", upstream: UpstreamGCP, wantKey: "photos/a.jpg", wantETag: "\"2218880ef78838266ecd7d4c1b742a0e\""},
		{name: "rustfs", upstream: UpstreamRustFS, wantKey: "photos/a.jpg", wantETag: "\"d41d8cd98f00b204e9800998ecf8427e\""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			fixture := readListFixture(t, "ListObjects", tt.name)

			got, err := ParseListObjects(tt.upstream, fixture.Response)
			if err != nil {
				t.Fatalf("ParseListObjects returned error: %v", err)
			}
			if len(got.Objects) != 2 {
				t.Fatalf("object count = %d, want 2", len(got.Objects))
			}
			if got.Objects[0].Key != tt.wantKey {
				t.Fatalf("first key = %q, want %q", got.Objects[0].Key, tt.wantKey)
			}
			if got.Objects[0].ETag != tt.wantETag {
				t.Fatalf("first etag = %q, want %q", got.Objects[0].ETag, tt.wantETag)
			}
		})
	}
}

func TestAttributesFromListedObject(t *testing.T) {
	object := ListedObject{
		Key:          "photos/a.jpg",
		ETag:         "\"fba9dede5f27731c9771645a39863328\"",
		Size:         434234,
		LastModified: mustTime(t, "2026-06-26T01:00:00Z"),
		StorageClass: "STANDARD",
	}
	want := storage.ObjectAttributes{
		"upstream": map[string]any{
			"etag":          "\"fba9dede5f27731c9771645a39863328\"",
			"size":          int64(434234),
			"last_modified": "2026-06-26T01:00:00Z",
			"s3": map[string]any{
				"storage_class": "STANDARD",
			},
		},
	}

	got := AttributesFromListedObject(object)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("AttributesFromListedObject mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func readListFixture(t *testing.T, operation string, upstream string) rawFixture {
	t.Helper()

	path := filepath.Join("testdata", "mocks", operation, upstream+".json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %s: %v", path, err)
	}

	var fixture rawFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture %s: %v", path, err)
	}

	return fixture
}

func mustTime(t *testing.T, value string) time.Time {
	t.Helper()

	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		t.Fatalf("parse time %q: %v", value, err)
	}

	return parsed
}
