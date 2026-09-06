package httpserver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/elei-io/pithosys/apps/api/internal/config"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
)

func TestNewConfiguresServer(t *testing.T) {
	srv := New(testDeps())

	if srv.Addr != ":9090" {
		t.Fatalf("Addr = %q, want :9090", srv.Addr)
	}

	if srv.ReadHeaderTimeout == 0 {
		t.Fatal("ReadHeaderTimeout is zero")
	}

	if srv.ReadTimeout == 0 {
		t.Fatal("ReadTimeout is zero")
	}

	if srv.WriteTimeout == 0 {
		t.Fatal("WriteTimeout is zero")
	}

	if srv.IdleTimeout == 0 {
		t.Fatal("IdleTimeout is zero")
	}
}

func TestHealthz(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/healthz", nil)
	rec := httptest.NewRecorder()

	Handler(testDeps()).ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}

	if got, want := rec.Header().Get("Content-Type"), "application/json"; got != want {
		t.Fatalf("Content-Type = %q, want %q", got, want)
	}

	var body struct {
		Service string `json:"service"`
		Status  string `json:"status"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode health response: %v", err)
	}

	if body.Service != "pithosys-api" {
		t.Fatalf("service = %q, want pithosys-api", body.Service)
	}

	if body.Status != "ok" {
		t.Fatalf("status = %q, want ok", body.Status)
	}
}

func TestOpenAPI(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/openapi.json", nil)
	rec := httptest.NewRecorder()

	Handler(testDeps()).ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}

	var spec struct {
		Info struct {
			Title       string `json:"title"`
			Version     string `json:"version"`
			Description string `json:"description"`
		} `json:"info"`
		Paths   map[string]any `json:"paths"`
		Servers []struct {
			URL         string `json:"url"`
			Description string `json:"description"`
		} `json:"servers"`
		Tags []struct {
			Name        string `json:"name"`
			Description string `json:"description"`
		} `json:"tags"`
	}

	if err := json.Unmarshal(rec.Body.Bytes(), &spec); err != nil {
		t.Fatalf("decode OpenAPI response: %v", err)
	}

	if spec.Info.Title != "Pithosys API" {
		t.Fatalf("title = %q, want Pithosys API", spec.Info.Title)
	}

	if spec.Info.Version != "0.1.0" {
		t.Fatalf("version = %q, want 0.1.0", spec.Info.Version)
	}

	if spec.Info.Description == "" {
		t.Fatal("description is empty")
	}

	if _, ok := spec.Paths["/api/healthz"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/healthz")
	}
	if _, ok := spec.Paths["/api/job-runs"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/job-runs")
	}
	if _, ok := spec.Paths["/api/bucket-events"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/bucket-events")
	}
	if _, ok := spec.Paths["/api/job-runs/stats"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/job-runs/stats")
	}
	if _, ok := spec.Paths["/api/bucket-events/stats"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/bucket-events/stats")
	}
	if _, ok := spec.Paths["/api/objects"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/objects")
	}
	if _, ok := spec.Paths["/api/search/validate"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/search/validate")
	}
	if _, ok := spec.Paths["/api/search"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/search")
	}
	if _, ok := spec.Paths["/api/buckets/{id}/sync"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/buckets/{id}/sync")
	}
	if _, ok := spec.Paths["/api/buckets/{id}/scan"]; !ok {
		t.Fatal("OpenAPI spec does not include /api/buckets/{id}/scan")
	}
	bucketPath, ok := spec.Paths["/api/buckets/{id}"].(map[string]any)
	if !ok {
		t.Fatal("OpenAPI spec does not include /api/buckets/{id}")
	}
	if _, ok := bucketPath["delete"]; !ok {
		t.Fatal("OpenAPI spec does not include DELETE /api/buckets/{id}")
	}

	if len(spec.Servers) == 0 || spec.Servers[0].URL != "/api" {
		t.Fatalf("servers = %#v, want first URL /api", spec.Servers)
	}

	if len(spec.Tags) == 0 || spec.Tags[0].Name != "System" {
		t.Fatalf("tags = %#v, want System tag", spec.Tags)
	}
}

func TestDocs(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/docs", nil)
	rec := httptest.NewRecorder()

	Handler(testDeps()).ServeHTTP(rec, req)

	if rec.Code != http.StatusMovedPermanently && rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d or %d", rec.Code, http.StatusMovedPermanently, http.StatusOK)
	}
}

func testDeps() deps.Dependencies {
	return deps.Dependencies{
		Config: config.Config{HTTPAddr: ":9090"},
	}
}
