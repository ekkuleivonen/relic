package jetstreamconsumer

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestDiffJetStreamConsumers(t *testing.T) {
	desired := map[string]storage.BucketJetStreamConfig{
		"bucket_a": {
			URL:      "nats://127.0.0.1:4222",
			Stream:   "STREAM-A",
			Subject:  "subject.a",
			Consumer: "consumer-a",
		},
		"bucket_b": {
			URL:      "nats://127.0.0.1:4222",
			Stream:   "STREAM-B",
			Subject:  "subject.b",
			Consumer: "consumer-b",
		},
	}
	running := map[string]storage.BucketJetStreamConfig{
		"bucket_a": desired["bucket_a"],
		"bucket_c": {
			URL:      "nats://127.0.0.1:4222",
			Stream:   "STREAM-C",
			Subject:  "subject.c",
			Consumer: "consumer-c",
		},
	}

	toStart, toStop, unchanged := diffJetStreamConsumers(desired, running)

	if len(unchanged) != 1 || unchanged[0] != "bucket_a" {
		t.Fatalf("unchanged = %#v, want [bucket_a]", unchanged)
	}
	if len(toStart) != 1 || toStart[0] != "bucket_b" {
		t.Fatalf("toStart = %#v, want [bucket_b]", toStart)
	}
	if len(toStop) != 1 || toStop[0] != "bucket_c" {
		t.Fatalf("toStop = %#v, want [bucket_c]", toStop)
	}
}

func TestDiffJetStreamConsumersRestartsOnConfigChange(t *testing.T) {
	desired := map[string]storage.BucketJetStreamConfig{
		"bucket_a": {
			URL:      "nats://127.0.0.1:4222",
			Stream:   "STREAM-A",
			Subject:  "subject.a",
			Consumer: "consumer-a",
		},
	}
	running := map[string]storage.BucketJetStreamConfig{
		"bucket_a": {
			URL:      "nats://127.0.0.1:4222",
			Stream:   "STREAM-A",
			Subject:  "subject.changed",
			Consumer: "consumer-a",
		},
	}

	toStart, toStop, unchanged := diffJetStreamConsumers(desired, running)

	if len(unchanged) != 0 {
		t.Fatalf("unchanged = %#v, want none", unchanged)
	}
	if len(toStart) != 1 || toStart[0] != "bucket_a" {
		t.Fatalf("toStart = %#v, want [bucket_a]", toStart)
	}
	if len(toStop) != 1 || toStop[0] != "bucket_a" {
		t.Fatalf("toStop = %#v, want [bucket_a]", toStop)
	}
}

func TestNewConsumerRequiresBucketID(t *testing.T) {
	_, err := NewConsumer(ConsumerOptions{
		Store:   &storage.Store{},
		URL:     "nats://127.0.0.1:4222",
		Stream:  "STREAM",
		Subject: "subject",
	})
	if err == nil {
		t.Fatal("NewConsumer error = nil, want validation error")
	}
}
