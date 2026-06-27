package s3events

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

func TestParseLegacyRustFSSnakeCasePayload(t *testing.T) {
	body := []byte(`{
		"event_name": "ObjectCreatedPut",
		"key": "relic-fixtures/photos/a.jpg",
		"records": [{
			"eventVersion": "2.1",
			"eventSource": "rustfs:s3",
			"eventTime": "2026-06-26T01:00:00.000Z",
			"eventName": "ObjectCreatedPut",
			"s3": {
				"bucket": {"name": "relic-fixtures"},
				"object": {"key": "photos/a.jpg", "size": 434234, "eTag": "fba9dede5f27731c9771645a39863328"}
			}
		}]
	}`)

	got, err := Parse(body)
	if err != nil {
		t.Fatalf("Parse() error = %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("Parse() returned %d events, want 1", len(got))
	}
	if got[0].Upstream != s3compat.UpstreamRustFS {
		t.Fatalf("Upstream = %q, want %q", got[0].Upstream, s3compat.UpstreamRustFS)
	}
	if got[0].Action != EventActionImport {
		t.Fatalf("Action = %q, want %q", got[0].Action, EventActionImport)
	}
	if got[0].Key != "photos/a.jpg" {
		t.Fatalf("Key = %q, want photos/a.jpg", got[0].Key)
	}
}
