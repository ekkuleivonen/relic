package storage

import (
	"context"
	"testing"
	"time"
)

func TestUpstreamEventStoreCreateLockAndMarkProcessed(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	events := store.UpstreamEvents()
	created, err := events.CreateUpstreamEvent(ctx, CreateUpstreamEventParams{
		UpstreamBucketName: "upstream-events-test",
		EventName:          "ObjectCreated:Put",
		ObjectKey:          "photos/a.jpg",
		Envelope:           JobRunPayload{"event": "ObjectCreated:Put"},
		DedupeKey:          "dedupe-" + time.Now().Format("20060102150405.000000000"),
		Transport:          UpstreamEventTransportWebhook,
	})
	if err != nil {
		t.Fatalf("CreateUpstreamEvent returned error: %v", err)
	}
	t.Cleanup(func() {
		_, _ = store.pool.Exec(context.Background(), "DELETE FROM upstream_events WHERE id = $1", created.ID)
	})

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
}
