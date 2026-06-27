package storage

import (
	"fmt"
	"strings"
)

type BucketJetStreamConfig struct {
	URL      string
	Stream   string
	Subject  string
	Consumer string
}

func (c BucketJetStreamConfig) Equal(other BucketJetStreamConfig) bool {
	return c.URL == other.URL &&
		c.Stream == other.Stream &&
		c.Subject == other.Subject &&
		c.Consumer == other.Consumer
}

func DefaultJetStreamConsumerName(bucketID string) string {
	return "relic-" + bucketID
}

func ParseBucketJetStreamConfig(bucketID string, config BucketUpstreamConfig) (BucketJetStreamConfig, bool, error) {
	jetstream, err := jetstreamConfigMap(config)
	if err != nil {
		return BucketJetStreamConfig{}, false, err
	}
	if jetstream == nil {
		return BucketJetStreamConfig{}, false, nil
	}

	url, err := jetstreamStringConfig(jetstream, "url")
	if err != nil {
		return BucketJetStreamConfig{}, false, err
	}
	stream, err := jetstreamStringConfig(jetstream, "stream")
	if err != nil {
		return BucketJetStreamConfig{}, false, err
	}
	subject, err := jetstreamStringConfig(jetstream, "subject")
	if err != nil {
		return BucketJetStreamConfig{}, false, err
	}
	consumer, err := jetstreamStringConfig(jetstream, "consumer")
	if err != nil {
		return BucketJetStreamConfig{}, false, err
	}

	url = strings.TrimSpace(url)
	stream = strings.TrimSpace(stream)
	subject = strings.TrimSpace(subject)
	consumer = strings.TrimSpace(consumer)

	populated := 0
	if url != "" {
		populated++
	}
	if stream != "" {
		populated++
	}
	if subject != "" {
		populated++
	}

	switch populated {
	case 0:
		return BucketJetStreamConfig{}, false, nil
	case 3:
		if consumer == "" {
			consumer = DefaultJetStreamConsumerName(bucketID)
		}
		return BucketJetStreamConfig{
			URL:      url,
			Stream:   stream,
			Subject:  subject,
			Consumer: consumer,
		}, true, nil
	default:
		return BucketJetStreamConfig{}, false, fmt.Errorf("upstream_config.jetstream requires url, stream, and subject when jetstream ingest is configured")
	}
}

func jetstreamConfigMap(config BucketUpstreamConfig) (map[string]any, error) {
	value, ok := config["jetstream"]
	if !ok || value == nil {
		return nil, nil
	}

	typed, ok := value.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("upstream_config.jetstream must be an object")
	}

	return typed, nil
}

func jetstreamStringConfig(config map[string]any, key string) (string, error) {
	value, ok := config[key]
	if !ok || value == nil {
		return "", nil
	}

	typed, ok := value.(string)
	if !ok {
		return "", fmt.Errorf("upstream_config.jetstream.%s must be a string", key)
	}

	return typed, nil
}
