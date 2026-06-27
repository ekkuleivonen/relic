package storage

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

var ErrUpstreamEventDuplicate = errors.New("upstream event duplicate")

type UpstreamEventTransport string

const (
	UpstreamEventTransportWebhook   UpstreamEventTransport = "webhook"
	UpstreamEventTransportJetstream UpstreamEventTransport = "jetstream"
)

type UpstreamEventState string

const (
	UpstreamEventStatePending   UpstreamEventState = "pending"
	UpstreamEventStateProcessed UpstreamEventState = "processed"
	UpstreamEventStateSkipped   UpstreamEventState = "skipped"
	UpstreamEventStateFailed    UpstreamEventState = "failed"
)

type UpstreamEventRepository interface {
	CreateUpstreamEvent(context.Context, CreateUpstreamEventParams) (UpstreamEvent, error)
	GetUpstreamEvent(context.Context, string) (UpstreamEvent, error)
	LockPendingEvents(context.Context, int) ([]UpstreamEvent, error)
	MarkUpstreamEvent(context.Context, MarkUpstreamEventParams) error
}

type UpstreamEventStore struct {
	runner Runner
}

func NewUpstreamEventStore(runner Runner) *UpstreamEventStore {
	return &UpstreamEventStore{runner: runner}
}

type UpstreamEvent struct {
	ID                 string
	BucketID           string
	UpstreamBucketName string
	UpstreamPlatform   string
	UpstreamRegion     string
	UpstreamOrigin     string
	EventName          string
	ObjectKey          string
	Envelope           JobRunPayload
	DedupeKey          string
	Transport          UpstreamEventTransport
	State              UpstreamEventState
	EventTime          *time.Time
	ReceivedAt         time.Time
	ProcessedAt        *time.Time
	ErrorMessage       string
	CreatedAt          time.Time
	UpdatedAt          time.Time
}

type CreateUpstreamEventParams struct {
	BucketID           *string
	UpstreamBucketName string
	UpstreamPlatform   string
	UpstreamRegion     string
	UpstreamOrigin     string
	EventName          string
	ObjectKey          string
	Envelope           JobRunPayload
	DedupeKey          string
	Transport          UpstreamEventTransport
	EventTime          *time.Time
}

type MarkUpstreamEventParams struct {
	ID           string
	State        UpstreamEventState
	ErrorMessage string
}

type IngestUpstreamEventsResult struct {
	Accepted  int
	Duplicate int
	Ignored   int
	EventIDs  []string
}

func (s *UpstreamEventStore) CreateUpstreamEvent(ctx context.Context, params CreateUpstreamEventParams) (UpstreamEvent, error) {
	id, err := newUpstreamEventID()
	if err != nil {
		return UpstreamEvent{}, err
	}

	envelope, err := encodeJobRunPayload(params.Envelope)
	if err != nil {
		return UpstreamEvent{}, err
	}

	event, err := scanUpstreamEvent(s.runner.QueryRow(ctx, `
		INSERT INTO upstream_events (
			id,
			bucket_id,
			upstream_bucket_name,
			upstream_platform,
			upstream_region,
			upstream_origin,
			event_name,
			object_key,
			envelope,
			dedupe_key,
			transport,
			event_time
		) VALUES (
			$1,
			$2,
			$3,
			$4,
			$5,
			$6,
			$7,
			$8,
			$9::jsonb,
			$10,
			$11,
			$12
		)
		RETURNING `+upstreamEventSelectColumns+`
	`, id, params.BucketID, params.UpstreamBucketName, params.UpstreamPlatform, params.UpstreamRegion, params.UpstreamOrigin, params.EventName, params.ObjectKey, envelope, params.DedupeKey, params.Transport, params.EventTime))
	if err != nil {
		return UpstreamEvent{}, mapCreateUpstreamEventError(err)
	}

	return event, nil
}

func (s *UpstreamEventStore) GetUpstreamEvent(ctx context.Context, id string) (UpstreamEvent, error) {
	return scanUpstreamEvent(s.runner.QueryRow(ctx, `
		SELECT `+upstreamEventSelectColumns+`
		FROM upstream_events
		WHERE id = $1
	`, id))
}

func (s *UpstreamEventStore) LockPendingEvents(ctx context.Context, limit int) ([]UpstreamEvent, error) {
	if limit <= 0 {
		limit = 100
	}

	rows, err := s.runner.Query(ctx, `
		SELECT `+upstreamEventSelectColumns+`
		FROM upstream_events
		WHERE state = 'pending'
		ORDER BY received_at ASC, id ASC
		FOR UPDATE SKIP LOCKED
		LIMIT $1
	`, limit)
	if err != nil {
		return nil, fmt.Errorf("lock pending upstream events: %w", err)
	}
	defer rows.Close()

	events := []UpstreamEvent{}
	for rows.Next() {
		event, err := scanUpstreamEventRow(rows)
		if err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("lock pending upstream events: %w", err)
	}

	return events, nil
}

func (s *UpstreamEventStore) MarkUpstreamEvent(ctx context.Context, params MarkUpstreamEventParams) error {
	tag, err := s.runner.Exec(ctx, `
		UPDATE upstream_events
		SET
			state = $2,
			error_message = NULLIF($3, ''),
			processed_at = CASE WHEN $2 IN ('processed', 'skipped', 'failed') THEN now() ELSE processed_at END,
			updated_at = now()
		WHERE id = $1
	`, params.ID, params.State, params.ErrorMessage)
	if err != nil {
		return fmt.Errorf("mark upstream event: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}

	return nil
}

const upstreamEventSelectColumns = `
	id,
	bucket_id,
	upstream_bucket_name,
	upstream_platform,
	upstream_region,
	upstream_origin,
	event_name,
	object_key,
	envelope,
	dedupe_key,
	transport,
	state,
	event_time,
	received_at,
	processed_at,
	error_message,
	created_at,
	updated_at
`

func scanUpstreamEvent(row pgx.Row) (UpstreamEvent, error) {
	return scanUpstreamEventRow(row)
}

func scanUpstreamEventRow(row pgx.Row) (UpstreamEvent, error) {
	var (
		event         UpstreamEvent
		bucketID      sql.NullString
		transport     string
		state         string
		envelopeBytes []byte
		eventTime     sql.NullTime
		processedAt   sql.NullTime
		errorMessage  sql.NullString
	)

	err := row.Scan(
		&event.ID,
		&bucketID,
		&event.UpstreamBucketName,
		&event.UpstreamPlatform,
		&event.UpstreamRegion,
		&event.UpstreamOrigin,
		&event.EventName,
		&event.ObjectKey,
		&envelopeBytes,
		&event.DedupeKey,
		&transport,
		&state,
		&eventTime,
		&event.ReceivedAt,
		&processedAt,
		&errorMessage,
		&event.CreatedAt,
		&event.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return UpstreamEvent{}, ErrNotFound
		}
		return UpstreamEvent{}, fmt.Errorf("scan upstream event: %w", err)
	}

	if bucketID.Valid {
		event.BucketID = bucketID.String
	}
	event.Transport = UpstreamEventTransport(transport)
	event.State = UpstreamEventState(state)
	if eventTime.Valid {
		value := eventTime.Time
		event.EventTime = &value
	}
	if processedAt.Valid {
		value := processedAt.Time
		event.ProcessedAt = &value
	}
	if errorMessage.Valid {
		event.ErrorMessage = errorMessage.String
	}
	if err := json.Unmarshal(envelopeBytes, &event.Envelope); err != nil {
		return UpstreamEvent{}, fmt.Errorf("decode upstream event envelope: %w", err)
	}
	if event.Envelope == nil {
		event.Envelope = JobRunPayload{}
	}

	return event, nil
}

func mapCreateUpstreamEventError(err error) error {
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" {
		return ErrUpstreamEventDuplicate
	}

	return fmt.Errorf("create upstream event: %w", err)
}

func newUpstreamEventID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate upstream event id: %w", err)
	}

	return "upevt_" + hex.EncodeToString(random), nil
}

func UpstreamEventDedupeKey(platform, origin, bucketName, eventName, objectKey, eventID string, eventTime time.Time) string {
	if eventID != "" {
		return platform + ":" + origin + ":" + bucketName + ":" + eventName + ":" + objectKey + ":" + eventID
	}

	material := platform + "|" + origin + "|" + bucketName + "|" + eventName + "|" + objectKey + "|" + eventTime.UTC().Format(time.RFC3339Nano)
	sum := sha256.Sum256([]byte(material))

	return hex.EncodeToString(sum[:])
}

func (event UpstreamEvent) EventMatch(objectKey string) BucketEventMatch {
	key := objectKey
	if key == "" {
		key = event.ObjectKey
	}

	return BucketEventMatch{
		Platform:           event.UpstreamPlatform,
		Region:             event.UpstreamRegion,
		Origin:             event.UpstreamOrigin,
		UpstreamBucketName: event.UpstreamBucketName,
		ObjectKey:          key,
	}
}
