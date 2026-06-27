package s3events

import (
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

func TestParseNotificationFixtures(t *testing.T) {
	tests := []struct {
		fixture    string
		wantAction EventAction
		wantBucket string
		wantKey    string
		wantETag   string
		wantSize   int64
		wantTime   string
		wantID     string
	}{
		{
			fixture:    "aws_object_created.json",
			wantAction: EventActionImport,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/a.jpg",
			wantETag:   "fba9dede5f27731c9771645a39863328",
			wantSize:   434234,
			wantTime:   "2026-06-26T01:00:00Z",
		},
		{
			fixture:    "aws_object_removed.json",
			wantAction: EventActionRemove,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/b.jpg",
			wantTime:   "2026-06-26T01:05:00Z",
		},
		{
			fixture:    "aws_sns_object_created.json",
			wantAction: EventActionImport,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/a.jpg",
			wantETag:   "fba9dede5f27731c9771645a39863328",
			wantSize:   434234,
			wantTime:   "2026-06-26T01:00:00Z",
		},
		{
			fixture:    "aws_eventbridge_object_created.json",
			wantAction: EventActionImport,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/a.jpg",
			wantETag:   "fba9dede5f27731c9771645a39863328",
			wantSize:   434234,
			wantTime:   "2026-06-26T01:00:00Z",
		},
		{
			fixture:    "b2_object_created.json",
			wantAction: EventActionImport,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/a.jpg",
			wantSize:   434234,
			wantTime:   "2024-06-26T09:15:09.123Z",
			wantID:     "ba9a8e4eacda8b4b7d23a0ec1f04046342c319f3c608903e794c45a5b57184be",
		},
		{
			fixture:    "b2_object_removed.json",
			wantAction: EventActionRemove,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/b.jpg",
			wantTime:   "2024-06-26T09:20:09.123Z",
			wantID:     "c1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f80",
		},
		{
			fixture:    "gcp_object_created.json",
			wantAction: EventActionImport,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/a.jpg",
			wantETag:   "fba9dede5f27731c9771645a39863328",
			wantSize:   434234,
			wantTime:   "2026-06-26T01:00:00Z",
		},
		{
			fixture:    "gcp_object_removed.json",
			wantAction: EventActionRemove,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/b.jpg",
			wantTime:   "2026-06-26T01:05:00Z",
		},
		{
			fixture:    "r2_object_created.json",
			wantAction: EventActionImport,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/a.jpg",
			wantETag:   "fba9dede5f27731c9771645a39863328",
			wantSize:   434234,
			wantTime:   "2026-06-26T01:00:00Z",
		},
		{
			fixture:    "r2_object_removed.json",
			wantAction: EventActionRemove,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/b.jpg",
			wantTime:   "2026-06-26T01:05:00Z",
		},
		{
			fixture:    "rustfs_object_created.json",
			wantAction: EventActionImport,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/a.jpg",
			wantETag:   "fba9dede5f27731c9771645a39863328",
			wantSize:   434234,
			wantTime:   "2026-06-26T01:00:00Z",
		},
		{
			fixture:    "rustfs_object_removed.json",
			wantAction: EventActionRemove,
			wantBucket: "relic-fixtures",
			wantKey:    "photos/b.jpg",
			wantTime:   "2026-06-26T01:05:00Z",
		},
	}

	for _, test := range tests {
		t.Run(test.fixture, func(t *testing.T) {
			fixture, err := loadNotificationFixture(test.fixture)
			if err != nil {
				t.Fatalf("loadNotificationFixture() error = %v", err)
			}

			got, err := Parse(fixture.Body)
			if err != nil {
				t.Fatalf("Parse() error = %v", err)
			}
			if len(got) != 1 {
				t.Fatalf("Parse() returned %d events, want 1", len(got))
			}

			event := got[0]
			if event.Upstream != fixture.Upstream {
				t.Fatalf("Upstream = %q, want %q", event.Upstream, fixture.Upstream)
			}
			if event.Action != test.wantAction {
				t.Fatalf("Action = %q, want %q", event.Action, test.wantAction)
			}
			if event.BucketName != test.wantBucket {
				t.Fatalf("BucketName = %q, want %q", event.BucketName, test.wantBucket)
			}
			if event.Key != test.wantKey {
				t.Fatalf("Key = %q, want %q", event.Key, test.wantKey)
			}
			if event.ETag != test.wantETag {
				t.Fatalf("ETag = %q, want %q", event.ETag, test.wantETag)
			}
			if event.Size != test.wantSize {
				t.Fatalf("Size = %d, want %d", event.Size, test.wantSize)
			}
			if !event.EventTime.Equal(mustTime(t, test.wantTime)) {
				t.Fatalf("EventTime = %s, want %s", event.EventTime, test.wantTime)
			}
			if test.wantID != "" && event.EventID != test.wantID {
				t.Fatalf("EventID = %q, want %q", event.EventID, test.wantID)
			}
		})
	}
}

func TestParseDetectsUpstreamFromS3CompatibleRecords(t *testing.T) {
	tests := []struct {
		name       string
		body       string
		wantSource s3compat.Upstream
	}{
		{
			name: "aws",
			body: `{"Records":[{"eventSource":"aws:s3","eventName":"ObjectCreated:Put","eventTime":"2026-06-26T01:00:00.000Z","s3":{"bucket":{"name":"relic-fixtures"},"object":{"key":"photos/a.jpg"}}}]}`,
			wantSource: s3compat.UpstreamAWS,
		},
		{
			name: "rustfs",
			body: `{"Records":[{"eventSource":"rustfs:s3","eventName":"s3:ObjectCreated:Put","eventTime":"2026-06-26T01:00:00.000Z","s3":{"bucket":{"name":"relic-fixtures"},"object":{"key":"photos/a.jpg"}}}]}`,
			wantSource: s3compat.UpstreamRustFS,
		},
		{
			name: "minio",
			body: `{"Records":[{"eventSource":"minio:s3","eventName":"s3:ObjectCreated:Put","eventTime":"2026-06-26T01:00:00.000Z","s3":{"bucket":{"name":"relic-fixtures"},"object":{"key":"photos/a.jpg"}}}]}`,
			wantSource: s3compat.UpstreamAWS,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, err := Parse([]byte(test.body))
			if err != nil {
				t.Fatalf("Parse() error = %v", err)
			}
			if len(got) != 1 {
				t.Fatalf("Parse() returned %d events, want 1", len(got))
			}
			if got[0].Upstream != test.wantSource {
				t.Fatalf("Upstream = %q, want %q", got[0].Upstream, test.wantSource)
			}
		})
	}
}

func TestParseIgnoresTaggingAndMetadataEvents(t *testing.T) {
	body := []byte(`{"Records":[{"eventSource":"aws:s3","eventName":"ObjectTagging:Put","eventTime":"2026-06-26T01:00:00.000Z","s3":{"bucket":{"name":"relic-fixtures"},"object":{"key":"photos/a.jpg"}}}]}`)

	got, err := Parse(body)
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("Parse() returned %d events, want 0", len(got))
	}
}

func TestParseSkipsRecordsWithEmptyObjectKey(t *testing.T) {
	body := []byte(`{"Records":[{"eventSource":"rustfs:s3","eventName":"s3:ObjectCreated:Put","eventTime":"2026-06-26T01:00:00.000Z","s3":{"bucket":{"name":"relic-fixtures"},"object":{"key":""}}}]}`)

	got, err := Parse(body)
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("Parse() returned %d events, want 0", len(got))
	}
}

func mustTime(t *testing.T, value string) time.Time {
	t.Helper()

	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		t.Fatalf("parse time %q: %v", value, err)
	}

	return parsed
}
