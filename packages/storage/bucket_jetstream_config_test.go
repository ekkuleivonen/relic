package storage

import "testing"

func TestParseBucketJetStreamConfigDisabledWhenMissing(t *testing.T) {
	_, enabled, err := ParseBucketJetStreamConfig("bucket_abc", BucketUpstreamConfig{})
	if err != nil {
		t.Fatalf("ParseBucketJetStreamConfig returned error: %v", err)
	}
	if enabled {
		t.Fatal("enabled = true, want false")
	}
}

func TestParseBucketJetStreamConfigDisabledWhenEmptyObject(t *testing.T) {
	_, enabled, err := ParseBucketJetStreamConfig("bucket_abc", BucketUpstreamConfig{
		"jetstream": map[string]any{},
	})
	if err != nil {
		t.Fatalf("ParseBucketJetStreamConfig returned error: %v", err)
	}
	if enabled {
		t.Fatal("enabled = true, want false")
	}
}

func TestParseBucketJetStreamConfigRequiresAllRequiredFields(t *testing.T) {
	_, enabled, err := ParseBucketJetStreamConfig("bucket_abc", BucketUpstreamConfig{
		"jetstream": map[string]any{
			"url": "nats://127.0.0.1:4222",
		},
	})
	if err == nil {
		t.Fatal("ParseBucketJetStreamConfig error = nil, want validation error")
	}
	if enabled {
		t.Fatal("enabled = true, want false")
	}
}

func TestParseBucketJetStreamConfigParsesValues(t *testing.T) {
	cfg, enabled, err := ParseBucketJetStreamConfig("bucket_abc", BucketUpstreamConfig{
		"jetstream": map[string]any{
			"url":      "nats://127.0.0.1:4222",
			"stream":   "BUCKET-TEST",
			"subject":  "storage.raw.test",
			"consumer": "custom-consumer",
		},
	})
	if err != nil {
		t.Fatalf("ParseBucketJetStreamConfig returned error: %v", err)
	}
	if !enabled {
		t.Fatal("enabled = false, want true")
	}
	if cfg.URL != "nats://127.0.0.1:4222" {
		t.Fatalf("url = %q", cfg.URL)
	}
	if cfg.Stream != "BUCKET-TEST" {
		t.Fatalf("stream = %q", cfg.Stream)
	}
	if cfg.Subject != "storage.raw.test" {
		t.Fatalf("subject = %q", cfg.Subject)
	}
	if cfg.Consumer != "custom-consumer" {
		t.Fatalf("consumer = %q", cfg.Consumer)
	}
}

func TestParseBucketJetStreamConfigDefaultsConsumerName(t *testing.T) {
	cfg, enabled, err := ParseBucketJetStreamConfig("bucket_abc", BucketUpstreamConfig{
		"jetstream": map[string]any{
			"url":     "nats://127.0.0.1:4222",
			"stream":  "BUCKET-TEST",
			"subject": "storage.raw.test",
		},
	})
	if err != nil {
		t.Fatalf("ParseBucketJetStreamConfig returned error: %v", err)
	}
	if !enabled {
		t.Fatal("enabled = false, want true")
	}
	if cfg.Consumer != "relic-bucket_abc" {
		t.Fatalf("consumer = %q, want relic-bucket_abc", cfg.Consumer)
	}
}

func TestParseBucketJetStreamConfigRejectsInvalidTypes(t *testing.T) {
	_, enabled, err := ParseBucketJetStreamConfig("bucket_abc", BucketUpstreamConfig{
		"jetstream": map[string]any{
			"url":     123,
			"stream":  "BUCKET-TEST",
			"subject": "storage.raw.test",
		},
	})
	if err == nil {
		t.Fatal("ParseBucketJetStreamConfig error = nil, want validation error")
	}
	if enabled {
		t.Fatal("enabled = true, want false")
	}
}
