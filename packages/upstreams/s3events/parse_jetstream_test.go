package s3events

import "testing"

func TestParseRustFSJetStreamPayload(t *testing.T) {
	body := []byte(`{"EventName":"s3:ObjectRemoved:Delete","Key":"juicefs/juicefs/meta/dump.json","Records":[{"eventVersion":"2.1","eventSource":"rustfs:s3","awsRegion":"","eventTime":"2026-06-27T04:17:28.001381834Z","eventName":"s3:ObjectRemoved:Delete","s3":{"bucket":{"name":"pithosys-test-01"},"object":{"key":"photos/a.jpg","eTag":"abc"}}}]}`)

	events, err := Parse(body)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}
	if len(events) != 1 {
		t.Fatalf("len(events) = %d, want 1", len(events))
	}
	if events[0].BucketName != "pithosys-test-01" {
		t.Fatalf("bucket = %q, want pithosys-test-01", events[0].BucketName)
	}
	if events[0].Key != "photos/a.jpg" {
		t.Fatalf("key = %q, want photos/a.jpg", events[0].Key)
	}
}
