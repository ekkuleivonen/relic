package upstreamcapture

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	"github.com/elei-io/pithosys/apps/api/internal/config"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
)

func TestListUpstreamCaptureFields(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := storage.SeedUpstreamCaptureFields(ctx, store.UpstreamCaptureFields()); err != nil {
		t.Fatalf("SeedUpstreamCaptureFields returned error: %v", err)
	}

	handler := testHandler(store)
	req := httptest.NewRequest(http.MethodGet, "/api/upstream-capture-fields", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var body []CaptureFieldResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode list response: %v", err)
	}
	if len(body) != len(storage.PlatformUpstreamCaptureFields()) {
		t.Fatalf("field count = %d, want %d", len(body), len(storage.PlatformUpstreamCaptureFields()))
	}
}

func TestCreateUpstreamCaptureField(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	handler := testHandler(store)
	req := httptest.NewRequest(
		http.MethodPost,
		"/api/upstream-capture-fields",
		strings.NewReader(`{
			"attribute_path":"upstream.vendor.deployment_id",
			"enabled":true,
			"capture_source":"head",
			"extractor_type":"response_header",
			"extractor_ref":"x-acme-deployment-id",
			"value_type":"string"
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusCreated, rec.Body.String())
	}

	var body CaptureFieldResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	if body.Origin != string(storage.CaptureFieldOriginUser) {
		t.Fatalf("origin = %q, want user", body.Origin)
	}
}

func TestPatchRequiredCaptureFieldRejected(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	if err := storage.SeedUpstreamCaptureFields(ctx, store.UpstreamCaptureFields()); err != nil {
		t.Fatalf("SeedUpstreamCaptureFields returned error: %v", err)
	}

	handler := testHandler(store)
	req := httptest.NewRequest(
		http.MethodPatch,
		"/api/upstream-capture-fields/upstream.head.etag",
		strings.NewReader(`{"enabled":false}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusUnprocessableEntity, rec.Body.String())
	}
}

func testHandler(store *storage.Store) http.Handler {
	mux := http.NewServeMux()
	api := humago.New(mux, huma.DefaultConfig("Test API", "0.0.0"))
	Register(api, deps.Dependencies{
		Config:  config.Config{HTTPAddr: ":9090"},
		Storage: store,
	}, "/api")

	return mux
}

func testStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	if err := testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
		return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
	}); err != nil {
		t.Fatal(testdb.MigrationTimeoutError(err))
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
