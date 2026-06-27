package upstreamevents

import (
	"context"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/testdb"
)

var (
	migrateIngestTestStoreOnce sync.Once
	migrateIngestTestStoreErr  error
)

func TestIngestS3NotificationJetstreamTransport(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	body := loadFixture(t, "rustfs_object_created.json")
	result, err := IngestS3Notification(
		ctx,
		store.UpstreamEvents(),
		body,
		storage.UpstreamEventTransportJetstream,
		nil,
	)
	if err != nil {
		t.Fatalf("IngestS3Notification returned error: %v", err)
	}
	if result.Accepted != 1 {
		t.Fatalf("accepted = %d, want 1", result.Accepted)
	}

	event, err := store.UpstreamEvents().GetUpstreamEvent(ctx, result.EventIDs[0])
	if err != nil {
		t.Fatalf("GetUpstreamEvent returned error: %v", err)
	}
	if event.Transport != storage.UpstreamEventTransportJetstream {
		t.Fatalf("transport = %q, want jetstream", event.Transport)
	}
	if event.UpstreamPlatform != "rustfs" {
		t.Fatalf("upstream platform = %q, want rustfs", event.UpstreamPlatform)
	}
	if event.ObjectKey != "photos/a.jpg" {
		t.Fatalf("object key = %q, want photos/a.jpg", event.ObjectKey)
	}
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	database, err := db.Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("connect test database: %v", err)
	}

	migrateIngestTestStoreOnce.Do(func() {
		migrateIngestTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "upstream_events", func() error {
			return storage.RunMigrations(ctx, databaseURL, "")
		})
	})
	if migrateIngestTestStoreErr != nil {
		database.Close()
		t.Fatal(testdb.MigrationTimeoutError(migrateIngestTestStoreErr))
	}

	store, err := storage.New(database)
	if err != nil {
		database.Close()
		t.Fatalf("create storage store: %v", err)
	}

	return store, func() {
		database.Close()
	}
}

func loadFixture(t *testing.T, name string) []byte {
	t.Helper()

	path := filepath.Join("..", "upstreams", "s3events", "testdata", "notifications", name)
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %s: %v", name, err)
	}

	return body
}
