package bucketevents

import (
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

type BucketEventResponse struct {
	ID           string                         `json:"id" example:"upevt_0123456789abcdef0123456789abcdef"`
	BucketID     string                         `json:"bucket_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	EventName    string                         `json:"event_name" example:"ObjectCreated:Put"`
	ObjectKey    string                         `json:"object_key" example:"photos/a.jpg"`
	Envelope     storage.JobRunPayload          `json:"envelope"`
	DedupeKey    string                         `json:"dedupe_key"`
	Transport    storage.UpstreamEventTransport `json:"transport" example:"jetstream"`
	State        storage.UpstreamEventState     `json:"state" example:"pending"`
	EventTime    *time.Time                     `json:"event_time,omitempty"`
	ReceivedAt   time.Time                      `json:"received_at"`
	ProcessedAt  *time.Time                     `json:"processed_at,omitempty"`
	ErrorMessage string                         `json:"error_message,omitempty"`
	CreatedAt    time.Time                      `json:"created_at"`
	UpdatedAt    time.Time                      `json:"updated_at"`
}

func BucketEventResponseFromStorage(event storage.UpstreamEvent) BucketEventResponse {
	return BucketEventResponse{
		ID:           event.ID,
		BucketID:     event.BucketID,
		EventName:    event.EventName,
		ObjectKey:    event.ObjectKey,
		Envelope:     event.Envelope,
		DedupeKey:    event.DedupeKey,
		Transport:    event.Transport,
		State:        event.State,
		EventTime:    event.EventTime,
		ReceivedAt:   event.ReceivedAt,
		ProcessedAt:  event.ProcessedAt,
		ErrorMessage: event.ErrorMessage,
		CreatedAt:    event.CreatedAt,
		UpdatedAt:    event.UpdatedAt,
	}
}
