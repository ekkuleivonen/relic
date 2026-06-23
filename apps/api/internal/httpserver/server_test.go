package httpserver

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ekkuleivonen/relic/apps/api/internal/config"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
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
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
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

	if body.Service != "relic-api" {
		t.Fatalf("service = %q, want relic-api", body.Service)
	}

	if body.Status != "ok" {
		t.Fatalf("status = %q, want ok", body.Status)
	}
}

func TestOpenAPI(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/openapi.json", nil)
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

	if spec.Info.Title != "Relic API" {
		t.Fatalf("title = %q, want Relic API", spec.Info.Title)
	}

	if spec.Info.Version != "0.1.0" {
		t.Fatalf("version = %q, want 0.1.0", spec.Info.Version)
	}

	if spec.Info.Description == "" {
		t.Fatal("description is empty")
	}

	if _, ok := spec.Paths["/healthz"]; !ok {
		t.Fatal("OpenAPI spec does not include /healthz")
	}

	if len(spec.Servers) == 0 || spec.Servers[0].URL != "/" {
		t.Fatalf("servers = %#v, want first URL /", spec.Servers)
	}

	if len(spec.Tags) == 0 || spec.Tags[0].Name != "System" {
		t.Fatalf("tags = %#v, want System tag", spec.Tags)
	}
}

func TestDocs(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/docs", nil)
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
