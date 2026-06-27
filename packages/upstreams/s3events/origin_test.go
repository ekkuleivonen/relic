package s3events

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

func TestNormalizedEventOriginKeyAWSRegion(t *testing.T) {
	event := NormalizedEvent{
		Upstream: s3compat.UpstreamAWS,
		Region:   "us-east-1",
	}

	if got, want := event.OriginKey(), "aws:us-east-1"; got != want {
		t.Fatalf("OriginKey() = %q, want %q", got, want)
	}
}

func TestNormalizedEventOriginKeyDeployment(t *testing.T) {
	event := NormalizedEvent{
		DeploymentID: "2369dcb4-348b-4d30-8fc9-61ab089ba4bc",
		EventSource:  "rustfs:s3",
	}

	if got, want := event.OriginKey(), "deployment:2369dcb4-348b-4d30-8fc9-61ab089ba4bc"; got != want {
		t.Fatalf("OriginKey() = %q, want %q", got, want)
	}
}

func TestNormalizedEventOriginKeyEventSource(t *testing.T) {
	event := NormalizedEvent{
		EventSource: "minio:s3",
	}

	if got, want := event.OriginKey(), "eventsource:minio:s3"; got != want {
		t.Fatalf("OriginKey() = %q, want %q", got, want)
	}
}

func TestOriginKeyFromEndpointSelfHosted(t *testing.T) {
	if got, want := OriginKeyFromEndpoint("https://minio.example.test:9000", ""), "endpoint:minio.example.test:9000"; got != want {
		t.Fatalf("OriginKeyFromEndpoint() = %q, want %q", got, want)
	}
}

func TestOriginKeyFromEndpointAWS(t *testing.T) {
	if got, want := OriginKeyFromEndpoint("https://s3.us-west-2.amazonaws.com", "us-west-2"), "aws:us-west-2"; got != want {
		t.Fatalf("OriginKeyFromEndpoint() = %q, want %q", got, want)
	}
}
