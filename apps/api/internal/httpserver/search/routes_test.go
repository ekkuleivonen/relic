package search

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	"github.com/ekkuleivonen/relic/apps/api/internal/config"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func TestExecuteSearchRequiresQuery(t *testing.T) {
	handler := testSearchHandler(&storage.Store{})

	req := httptest.NewRequest(http.MethodPost, "/api/search", strings.NewReader(`{"query":""}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusBadRequest, rec.Body.String())
	}
}

func TestExecuteSearchParseError(t *testing.T) {
	handler := testSearchHandler(&storage.Store{})

	req := httptest.NewRequest(http.MethodPost, "/api/search", strings.NewReader(`{"query":"SELECT * FROM objects"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusBadRequest, rec.Body.String())
	}
}

func TestExecuteSearchInfrastructureError(t *testing.T) {
	handler := testSearchHandler(&storage.Store{})

	req := httptest.NewRequest(http.MethodPost, "/api/search", strings.NewReader(`{"query":"FROM objects WHERE key = 'photos/a.jpg'"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusInternalServerError, rec.Body.String())
	}
}

func TestValidateSearchRequiresQuery(t *testing.T) {
	handler := testSearchHandler(&storage.Store{})

	req := httptest.NewRequest(http.MethodPost, "/api/search/validate", strings.NewReader(`{"query":""}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusBadRequest, rec.Body.String())
	}
}

func TestValidateSearchParseError(t *testing.T) {
	handler := testSearchHandler(&storage.Store{})

	req := httptest.NewRequest(http.MethodPost, "/api/search/validate", strings.NewReader(`{"query":"SELECT * FROM objects"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusBadRequest, rec.Body.String())
	}
}

func testSearchHandler(store *storage.Store) http.Handler {
	mux := http.NewServeMux()
	api := humago.New(mux, huma.DefaultConfig("Test API", "0.0.0"))
	Register(api, deps.Dependencies{
		Config:  config.Config{HTTPAddr: ":9090"},
		Storage: store,
	}, "/api")

	return mux
}
