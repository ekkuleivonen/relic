package httpserver

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/ekkuleivonen/relic/apps/api/internal/config"
)

func TestNewConfiguresServer(t *testing.T) {
	srv := New(config.Config{HTTPAddr: ":9090"})

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

	Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}

	if got, want := rec.Header().Get("Content-Type"), "application/json"; got != want {
		t.Fatalf("Content-Type = %q, want %q", got, want)
	}

	if got, want := rec.Body.String(), "{\"status\":\"ok\",\"service\":\"relic-api\"}\n"; got != want {
		t.Fatalf("body = %q, want %q", got, want)
	}
}
