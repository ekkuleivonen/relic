package upstreamevents

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	"github.com/ekkuleivonen/relic/apps/api/internal/config"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/testdb"
)

var (
	migrateUpstreamEventsTestStoreOnce sync.Once
	migrateUpstreamEventsTestStoreErr  error
)

func TestReceiveS3EventsStoresNotification(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	body := bytes.NewReader(loadFixtureBody(t, "aws_object_created.json"))
	handler := testHandler(store, "")

	req := httptest.NewRequest(http.MethodPost, "/api/upstream-events/s3", body)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusAccepted, rec.Body.String())
	}

	var response receiveS3EventsBody
	if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if response.Accepted != 1 {
		t.Fatalf("accepted = %d, want 1", response.Accepted)
	}
	if len(response.EventIDs) != 1 {
		t.Fatalf("event_ids = %#v, want one id", response.EventIDs)
	}

	event, err := store.UpstreamEvents().GetUpstreamEvent(ctx, response.EventIDs[0])
	if err != nil {
		t.Fatalf("GetUpstreamEvent returned error: %v", err)
	}
	if event.UpstreamBucketName != "relic-fixtures" {
		t.Fatalf("upstream bucket name = %q, want relic-fixtures", event.UpstreamBucketName)
	}
	if event.ObjectKey != "photos/a.jpg" {
		t.Fatalf("object key = %q, want photos/a.jpg", event.ObjectKey)
	}
	if event.UpstreamOrigin != "aws:us-east-1" {
		t.Fatalf("upstream origin = %q, want aws:us-east-1", event.UpstreamOrigin)
	}
	if event.State != storage.UpstreamEventStatePending {
		t.Fatalf("state = %q, want pending", event.State)
	}
}

func TestReceiveS3EventsRequiresWebhookSecretWhenConfigured(t *testing.T) {
	store, cleanup := testStore(t, context.Background())
	defer cleanup()

	handler := testHandler(store, "secret-token")
	req := httptest.NewRequest(http.MethodPost, "/api/upstream-events/s3", bytes.NewReader(loadFixtureBody(t, "aws_object_created.json")))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusUnauthorized, rec.Body.String())
	}
}

func TestReceiveS3EventsAcceptsDuplicateNotifications(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	handler := testHandler(store, "")
	body := loadFixtureBody(t, "aws_object_created.json")

	req := httptest.NewRequest(http.MethodPost, "/api/upstream-events/s3", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("first request status = %d, want %d; body = %s", rec.Code, http.StatusAccepted, rec.Body.String())
	}

	req = httptest.NewRequest(http.MethodPost, "/api/upstream-events/s3", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("second request status = %d, want %d; body = %s", rec.Code, http.StatusAccepted, rec.Body.String())
	}

	var response receiveS3EventsBody
	if err := json.Unmarshal(rec.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if response.Duplicate != 1 {
		t.Fatalf("duplicate = %d, want 1", response.Duplicate)
	}
}

func testHandler(store *storage.Store, webhookSecret string) http.Handler {
	mux := http.NewServeMux()
	api := humago.New(mux, huma.DefaultConfig("Test API", "0.0.0"))
	Register(api, deps.Dependencies{
		Config: config.Config{
			HTTPAddr:                    ":9090",
			UpstreamEventsWebhookSecret: webhookSecret,
		},
		Storage: store,
	}, "/api")

	return mux
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateUpstreamEventsTestStoreOnce.Do(func() {
		migrateUpstreamEventsTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "upstream_events", func() error {
			return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateUpstreamEventsTestStoreErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateUpstreamEventsTestStoreErr))
	}

	pool, err := db.Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Connect returned error: %v", err)
	}

	store, err := storage.New(pool)
	if err != nil {
		pool.Close()
		t.Fatalf("New returned error: %v", err)
	}

	return store, pool.Close
}

func loadFixtureBody(t *testing.T, name string) []byte {
	t.Helper()

	path := filepath.Join("../../../../packages/upstreams/s3events/testdata/notifications", name)
	encoded, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %q: %v", name, err)
	}

	var fixture struct {
		Body json.RawMessage `json:"body"`
	}
	if err := json.Unmarshal(encoded, &fixture); err != nil {
		t.Fatalf("decode fixture %q: %v", name, err)
	}

	return fixture.Body
}
