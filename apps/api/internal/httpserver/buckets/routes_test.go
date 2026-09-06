package buckets

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	"github.com/elei-io/pithosys/apps/api/internal/config"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/jobs"
	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
)

var (
	migrateTestStoreOnce sync.Once
	migrateTestStoreErr  error
)

func TestScanBucketRequiresStorage(t *testing.T) {
	handler := testBucketHandler(nil)

	req := httptest.NewRequest(http.MethodPost, "/api/buckets/bucket_missing/scan", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusInternalServerError, rec.Body.String())
	}
}

func TestScanBucketBucketNotFound(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	handler := testBucketHandler(store)

	req := httptest.NewRequest(http.MethodPost, "/api/buckets/bucket_nonexistent/scan", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusNotFound, rec.Body.String())
	}
}

func TestScanBucketCreatesJobRun(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	handler := testBucketHandler(store)

	req := httptest.NewRequest(http.MethodPost, "/api/buckets/"+bucket.ID+"/scan", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusAccepted, rec.Body.String())
	}

	var body jobs.JobRunResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode scan response: %v", err)
	}

	if body.Type != storage.JobTypeScanBucket {
		t.Fatalf("job type = %q, want %q", body.Type, storage.JobTypeScanBucket)
	}
	if body.State != storage.JobRunStatePending {
		t.Fatalf("job state = %q, want %q", body.State, storage.JobRunStatePending)
	}
	if body.RequestedByType != "api" {
		t.Fatalf("requested_by_type = %q, want api", body.RequestedByType)
	}
	if body.TargetType != "bucket" || body.TargetID != bucket.ID {
		t.Fatalf("target = %q/%q, want bucket/%q", body.TargetType, body.TargetID, bucket.ID)
	}
	if body.Input["bucket_id"] != bucket.ID {
		t.Fatalf("input bucket_id = %v, want %q", body.Input["bucket_id"], bucket.ID)
	}
	if _, ok := body.Input["prefix"]; ok {
		t.Fatalf("input prefix = %v, want absent", body.Input["prefix"])
	}

	persisted, err := store.JobRuns().GetJobRun(ctx, body.ID)
	if err != nil {
		t.Fatalf("GetJobRun returned error: %v", err)
	}
	if persisted.Type != storage.JobTypeScanBucket {
		t.Fatalf("persisted job type = %q, want %q", persisted.Type, storage.JobTypeScanBucket)
	}
}

func TestScanBucketWithOptionalPrefix(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "raw/")
	handler := testBucketHandler(store)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/buckets/"+bucket.ID+"/scan",
		strings.NewReader(`{"prefix":"photos/"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusAccepted, rec.Body.String())
	}

	var body jobs.JobRunResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode scan response: %v", err)
	}

	if body.Input["prefix"] != "photos/" {
		t.Fatalf("input prefix = %v, want photos/", body.Input["prefix"])
	}
}

func TestSyncBucketConflictWhenSyncTraceActive(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
			"objects":     []any{},
		},
	}); err != nil {
		t.Fatalf("CreateJobRun child returned error: %v", err)
	}

	handler := testBucketHandler(store)
	req := httptest.NewRequest(http.MethodPost, "/api/buckets/"+bucket.ID+"/sync", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusConflict {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusConflict, rec.Body.String())
	}
}

func TestSyncBucketResumesFailedSyncWithCheckpoint(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	bucket := createTestBucket(t, ctx, store, "")
	run, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   bucket.ID,
		Input: storage.JobRunPayload{
			"bucket_id": bucket.ID,
		},
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}
	if _, err := store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
		ID: run.ID,
		Progress: storage.JobRunPayload{
			"phase":            "listing",
			"objects_listed":   int64(59000),
			"listing_complete": false,
			"listing_checkpoint": map[string]any{
				"continuation_token": "token-590",
				"objects_listed":     int64(59000),
				"listing_complete":   false,
			},
			"import_objects_count": int64(59000),
		},
	}); err != nil {
		t.Fatalf("UpdateJobRunProgress returned error: %v", err)
	}
	if _, err := store.JobRuns().FailJobRun(ctx, storage.FailJobRunParams{
		ID:           run.ID,
		ErrorMessage: "upstream list timeout",
	}); err != nil {
		t.Fatalf("FailJobRun returned error: %v", err)
	}

	handler := testBucketHandler(store)
	req := httptest.NewRequest(http.MethodPost, "/api/buckets/"+bucket.ID+"/sync", nil)
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusAccepted, rec.Body.String())
	}

	var body jobs.JobRunResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode sync response: %v", err)
	}
	if body.ID != run.ID {
		t.Fatalf("job id = %q, want resumed job %q", body.ID, run.ID)
	}
	if body.State != storage.JobRunStatePending {
		t.Fatalf("job state = %q, want pending", body.State)
	}
}

func testBucketHandler(store *storage.Store) http.Handler {
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
	migrateTestStoreOnce.Do(func() {
		migrateTestStoreErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "buckets", func() error {
			return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateTestStoreErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateTestStoreErr))
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

func createTestBucket(t *testing.T, ctx context.Context, store *storage.Store, prefix string) storage.Bucket {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "scan-api-test-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.test",
		Region:      "us-east-1",
		BucketName:  "scan-api-test-data",
		Prefix:      prefix,
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

	return bucket
}
