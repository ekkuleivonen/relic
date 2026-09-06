package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestProtectRequestsRejectsCrossOriginWrites(t *testing.T) {
	handler := ProtectRequests(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusNoContent) }), "http://localhost:5173")
	for _, tc := range []struct {
		method, origin string
		status         int
	}{
		{"POST", "https://attacker.example", http.StatusForbidden},
		{"PATCH", "https://attacker.example", http.StatusForbidden},
		{"POST", "http://localhost:5173", http.StatusNoContent},
		{"GET", "https://attacker.example", http.StatusNoContent},
	} {
		t.Run(tc.method+tc.origin, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, "http://localhost:8080/api/buckets", nil)
			req.Header.Set("Origin", tc.origin)
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)
			if rec.Code != tc.status {
				t.Fatalf("status=%d, want %d", rec.Code, tc.status)
			}
		})
	}
}

func TestLoginRateLimitDoesNotTrustForwardedHeaders(t *testing.T) {
	calls := 0
	handler := LimitLogin(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++; w.WriteHeader(http.StatusNoContent) }))
	for i := 0; i < 11; i++ {
		req := httptest.NewRequest("POST", "/api/auth/login", nil)
		req.RemoteAddr = "192.0.2.1:12345"
		req.Header.Set("X-Forwarded-For", "203.0.113.2")
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if i == 10 && (rec.Code != http.StatusTooManyRequests || rec.Header().Get("Retry-After") == "") {
			t.Fatalf("rate limit response=%d", rec.Code)
		}
	}
	if calls != 10 {
		t.Fatalf("handler calls=%d, want 10", calls)
	}
}

func TestWriteAuthorizationDefaultsToAdmin(t *testing.T) {
	for _, path := range []string{"/api/buckets", "/api/buckets/id/sync", "/api/buckets/id/scan", "/api/upstream-capture-fields", "/api/detect-duplicates", "/api/future-feature"} {
		if !requiresAdmin(http.MethodPost, path) {
			t.Errorf("unprotected write: %s", path)
		}
	}
	for _, path := range []string{"/api/search", "/api/search/validate"} {
		if requiresAdmin(http.MethodPost, path) {
			t.Errorf("read-only search requires admin: %s", path)
		}
	}
	for _, path := range []string{"/api/auth/login-extra", "/api/auth/oidc/admin"} {
		if isPublicPath(path) {
			t.Errorf("unexpected auth bypass: %s", path)
		}
	}
}
