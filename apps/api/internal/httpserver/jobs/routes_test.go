package jobs

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	"github.com/elei-io/pithosys/apps/api/internal/config"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
)

func TestListJobRunsFiltersByTraceID(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	targetID := "bucket_jobs_trace_list_" + time.Now().Format("20060102150405.000000000")
	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun root returned error: %v", err)
	}

	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	}); err != nil {
		t.Fatalf("CreateJobRun child returned error: %v", err)
	}

	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeScanBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	}); err != nil {
		t.Fatalf("CreateJobRun other trace returned error: %v", err)
	}

	handler := testJobsHandler(store)
	req := httptest.NewRequest(http.MethodGet, "/api/job-runs?trace_id="+root.TraceID, nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var body listJobRunsBody
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode list response: %v", err)
	}
	if body.Total != 2 {
		t.Fatalf("total = %d, want 2", body.Total)
	}
	if len(body.JobRuns) != 2 {
		t.Fatalf("job run count = %d, want 2", len(body.JobRuns))
	}
	for _, run := range body.JobRuns {
		if run.TraceID != root.TraceID {
			t.Fatalf("trace_id = %q, want %q", run.TraceID, root.TraceID)
		}
	}
}

func TestGetJobRunIncludesTraceSummary(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	targetID := "bucket_jobs_trace_summary_" + time.Now().Format("20060102150405.000000000")
	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun root returned error: %v", err)
	}

	if _, err := store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
		ID: root.ID,
		Progress: storage.JobRunPayload{
			"phase":                "importing",
			"objects_listed":       1000,
			"import_objects_count": 1000,
		},
	}); err != nil {
		t.Fatalf("UpdateJobRunProgress returned error: %v", err)
	}

	doneChild, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun done child returned error: %v", err)
	}
	if _, err := store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{
		ID: doneChild.ID,
		Result: storage.JobRunPayload{
			"objects_imported": 500,
		},
	}); err != nil {
		t.Fatalf("SucceedJobRun done child returned error: %v", err)
	}

	if _, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	}); err != nil {
		t.Fatalf("CreateJobRun pending child returned error: %v", err)
	}

	handler := testJobsHandler(store)
	req := httptest.NewRequest(http.MethodGet, "/api/job-runs/"+root.ID+"?include=trace_summary", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var body JobRunDetailResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	if body.ID != root.ID {
		t.Fatalf("id = %q, want %q", body.ID, root.ID)
	}
	if body.TraceSummary == nil {
		t.Fatal("trace_summary = nil, want summary")
	}
	if body.TraceSummary.TraceID != root.TraceID {
		t.Fatalf("trace_summary.trace_id = %q, want %q", body.TraceSummary.TraceID, root.TraceID)
	}
	if body.TraceSummary.State != storage.JobRunStateRunning {
		t.Fatalf("trace_summary.state = %q, want running", body.TraceSummary.State)
	}
	if body.TraceSummary.Phase != "importing" {
		t.Fatalf("trace_summary.phase = %q, want importing", body.TraceSummary.Phase)
	}
	if body.TraceSummary.ObjectsListed != 1000 {
		t.Fatalf("trace_summary.objects_listed = %d, want 1000", body.TraceSummary.ObjectsListed)
	}
	if body.TraceSummary.ObjectsApplied.Import != 500 {
		t.Fatalf("trace_summary.objects_applied.import = %d, want 500", body.TraceSummary.ObjectsApplied.Import)
	}
	if body.TraceSummary.Batches.Import.Total != 2 {
		t.Fatalf("trace_summary.batches.import.total = %d, want 2", body.TraceSummary.Batches.Import.Total)
	}
}

func TestGetJobRunOmitsTraceSummaryByDefault(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   "bucket_jobs_trace_default_" + time.Now().Format("20060102150405.000000000"),
	})
	if err != nil {
		t.Fatalf("CreateJobRun returned error: %v", err)
	}

	handler := testJobsHandler(store)
	req := httptest.NewRequest(http.MethodGet, "/api/job-runs/"+root.ID, nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(rec.Body.Bytes(), &raw); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	if _, ok := raw["trace_summary"]; ok {
		t.Fatal("trace_summary present, want omitted by default")
	}
}

func TestGetJobRunTraceSummaryFromChildJob(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	targetID := "bucket_jobs_trace_child_" + time.Now().Format("20060102150405.000000000")
	root, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:       storage.JobTypeSyncBucket,
		TargetType: "bucket",
		TargetID:   targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun root returned error: %v", err)
	}

	child, err := store.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeImportObjects,
		RequestedByType: "job",
		RequestedByID:   root.ID,
		TargetType:      "bucket",
		TargetID:        targetID,
	})
	if err != nil {
		t.Fatalf("CreateJobRun child returned error: %v", err)
	}

	handler := testJobsHandler(store)
	req := httptest.NewRequest(http.MethodGet, "/api/job-runs/"+child.ID+"?include=trace_summary", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var body JobRunDetailResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	if body.ID != child.ID {
		t.Fatalf("id = %q, want %q", body.ID, child.ID)
	}
	if body.TraceSummary == nil {
		t.Fatal("trace_summary = nil, want summary")
	}
	if body.TraceSummary.RootJobRunID != root.ID {
		t.Fatalf("trace_summary.root_job_run_id = %q, want %q", body.TraceSummary.RootJobRunID, root.ID)
	}
}

func testJobsHandler(store *storage.Store) http.Handler {
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
	if err := testdb.MigrateIfNeeded(t, ctx, databaseURL, "jobs", func() error {
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
