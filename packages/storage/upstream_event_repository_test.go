package storage

import (
	"context"
	"testing"
	"time"

	"github.com/ekkuleivonen/relic/packages/secrets"
)

func TestUpstreamEventStoreCreateLockAndMarkProcessed(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket, err := store.Buckets().CreateBucket(ctx, CreateBucketParams{
		Name:        "upstream-events-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    BucketUpstreamS3,
		EndpointURL: "https://s3.amazonaws.com",
		Region:      "us-east-1",
		BucketName:  "upstream-events-test",
		EncryptedCredentials: secrets.Envelope{
			KeyID:      "local-dev",
			Algorithm:  secrets.AlgorithmXChaCha20Poly1305,
			Nonce:      []byte("012345678901234567890123"),
			Ciphertext: []byte("encrypted-credentials"),
		},
	})
	if err != nil {
		t.Fatalf("CreateBucket returned error: %v", err)
	}
	t.Cleanup(func() {
		_ = store.Buckets().DeleteBucket(context.Background(), bucket.ID)
	})

	events := store.UpstreamEvents()
	created, err := events.CreateUpstreamEvent(ctx, CreateUpstreamEventParams{
		BucketID:  bucket.ID,
		EventName: "ObjectCreated:Put",
		ObjectKey: "photos/a.jpg",
		Envelope:  JobRunPayload{"event": "ObjectCreated:Put"},
		DedupeKey: "dedupe-" + time.Now().Format("20060102150405.000000000"),
		Transport: UpstreamEventTransportJetstream,
	})
	if err != nil {
		t.Fatalf("CreateUpstreamEvent returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM upstream_events WHERE id = $1", created.ID)
	})

	if created.BucketID != bucket.ID {
		t.Fatalf("bucket_id = %q, want %q", created.BucketID, bucket.ID)
	}
	if created.State != UpstreamEventStatePending {
		t.Fatalf("state = %q, want pending", created.State)
	}

	var locked []UpstreamEvent
	if err := store.WithTx(ctx, func(ctx context.Context, tx *Tx) error {
		var err error
		locked, err = tx.UpstreamEvents().LockPendingEvents(ctx, 10)
		return err
	}); err != nil {
		t.Fatalf("WithTx lock returned error: %v", err)
	}
	if len(locked) != 1 || locked[0].ID != created.ID {
		t.Fatalf("locked events = %#v, want single event %q", locked, created.ID)
	}

	if err := store.UpstreamEvents().MarkUpstreamEvent(ctx, MarkUpstreamEventParams{
		ID:    created.ID,
		State: UpstreamEventStateProcessed,
	}); err != nil {
		t.Fatalf("MarkUpstreamEvent returned error: %v", err)
	}

	got, err := events.GetUpstreamEvent(ctx, created.ID)
	if err != nil {
		t.Fatalf("GetUpstreamEvent returned error: %v", err)
	}
	if got.State != UpstreamEventStateProcessed {
		t.Fatalf("state = %q, want processed", got.State)
	}
	if got.ProcessedAt == nil {
		t.Fatal("processed_at is nil, want timestamp")
	}

	listed, err := events.ListUpstreamEvents(ctx, ListUpstreamEventsParams{
		BucketID: bucket.ID,
		Limit:    50,
	})
	if err != nil {
		t.Fatalf("ListUpstreamEvents returned error: %v", err)
	}
	if len(listed) == 0 || listed[0].ID != created.ID {
		t.Fatalf("listed events = %#v, want created event %q first", listed, created.ID)
	}
}

func TestUpstreamEventDedupeKeyUsesBucketID(t *testing.T) {
	withEventID := UpstreamEventDedupeKey("bucket_abc", "ObjectCreated:Put", "photos/a.jpg", "evt-1", time.Time{})
	if withEventID != "bucket_abc:ObjectCreated:Put:photos/a.jpg:evt-1" {
		t.Fatalf("dedupe key = %q", withEventID)
	}

	eventTime := time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC)
	withoutEventID := UpstreamEventDedupeKey("bucket_abc", "ObjectCreated:Put", "photos/a.jpg", "", eventTime)
	if withoutEventID == "" || withoutEventID == withEventID {
		t.Fatalf("dedupe key = %q, want hashed fallback", withoutEventID)
	}
}
