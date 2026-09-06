package upstreamevents

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/upstreams/s3events"
)

func IngestS3Notification(
	ctx context.Context,
	events *storage.UpstreamEventStore,
	body []byte,
	bucketID string,
) (storage.IngestUpstreamEventsResult, error) {
	if strings.TrimSpace(bucketID) == "" {
		return storage.IngestUpstreamEventsResult{}, fmt.Errorf("ingest s3 notification: bucket id is required")
	}

	parsed, err := s3events.Parse(body)
	if err != nil {
		return storage.IngestUpstreamEventsResult{}, err
	}

	result := storage.IngestUpstreamEventsResult{}
	if len(parsed) == 0 {
		return result, nil
	}

	for _, event := range parsed {
		if event.Action == s3events.EventActionIgnore {
			result.Ignored++
			continue
		}

		var eventTime *time.Time
		if !event.EventTime.IsZero() {
			value := event.EventTime.UTC()
			eventTime = &value
		}

		envelope := storage.JobRunPayload{}
		if encoded, err := json.Marshal(event); err == nil {
			_ = json.Unmarshal(encoded, &envelope)
		}

		created, err := events.CreateUpstreamEvent(ctx, storage.CreateUpstreamEventParams{
			BucketID:  bucketID,
			EventName: event.EventName,
			ObjectKey: event.Key,
			Envelope:  envelope,
			DedupeKey: storage.UpstreamEventDedupeKey(
				bucketID,
				event.EventName,
				event.Key,
				event.EventID,
				event.EventTime,
			),
			Transport: storage.UpstreamEventTransportJetstream,
			EventTime: eventTime,
		})
		if errors.Is(err, storage.ErrUpstreamEventDuplicate) {
			result.Duplicate++
			continue
		}
		if err != nil {
			return result, fmt.Errorf("ingest upstream event for key %q: %w", event.Key, err)
		}

		result.Accepted++
		result.EventIDs = append(result.EventIDs, created.ID)
	}

	return result, nil
}
