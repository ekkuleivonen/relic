package httpserver

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

	"github.com/elei-io/pithosys/apps/api/internal/config"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/packages/auth"
	"github.com/elei-io/pithosys/packages/db"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/testdb"
)

var (
	migrateAuthIntegrationOnce sync.Once
	migrateAuthIntegrationErr  error
)

func TestAuthConfigReportsOIDCStatus(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/auth/config", nil)
	rec := httptest.NewRecorder()

	Handler(deps.Dependencies{
		Config: config.Config{HTTPAddr: ":9090"},
	}).ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var body struct {
		OIDCEnabled bool `json:"oidc_enabled"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.OIDCEnabled {
		t.Fatal("oidc_enabled = true, want false")
	}
}

func TestAuthLoginSessionAndProtectedRoute(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	loginReq := httptest.NewRequest(http.MethodPost, "/api/auth/login", strings.NewReader(`{"email":"admin@example.com","password":"secret-password"}`))
	loginReq.Header.Set("Content-Type", "application/json")
	loginRec := httptest.NewRecorder()
	handler.ServeHTTP(loginRec, loginReq)

	if loginRec.Code != http.StatusOK {
		t.Fatalf("login status = %d, want %d; body = %s", loginRec.Code, http.StatusOK, loginRec.Body.String())
	}

	cookies := loginRec.Result().Cookies()
	var sessionCookie *http.Cookie
	for _, cookie := range cookies {
		if cookie.Name == auth.SessionCookieName {
			sessionCookie = cookie
			break
		}
	}
	if sessionCookie == nil || sessionCookie.Value == "" {
		t.Fatal("login response did not set session cookie")
	}

	sessionReq := httptest.NewRequest(http.MethodGet, "/api/auth/session", nil)
	sessionReq.AddCookie(sessionCookie)
	sessionRec := httptest.NewRecorder()
	handler.ServeHTTP(sessionRec, sessionReq)

	if sessionRec.Code != http.StatusOK {
		t.Fatalf("session status = %d, want %d; body = %s", sessionRec.Code, http.StatusOK, sessionRec.Body.String())
	}

	bucketsReq := httptest.NewRequest(http.MethodGet, "/api/buckets", nil)
	bucketsReq.AddCookie(sessionCookie)
	bucketsRec := httptest.NewRecorder()
	handler.ServeHTTP(bucketsRec, bucketsReq)

	if bucketsRec.Code != http.StatusOK {
		t.Fatalf("buckets status = %d, want %d; body = %s", bucketsRec.Code, http.StatusOK, bucketsRec.Body.String())
	}

	unauthReq := httptest.NewRequest(http.MethodGet, "/api/buckets", nil)
	unauthRec := httptest.NewRecorder()
	handler.ServeHTTP(unauthRec, unauthReq)

	if unauthRec.Code != http.StatusUnauthorized {
		t.Fatalf("unauth buckets status = %d, want %d", unauthRec.Code, http.StatusUnauthorized)
	}
}

func TestAuthLoginRejectsUnknownUser(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	req := httptest.NewRequest(http.MethodPost, "/api/auth/login", strings.NewReader(`{"email":"missing@example.com","password":"secret-password"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusUnauthorized)
	}
}

func testAuthIntegrationHandler(t *testing.T, ctx context.Context) (http.Handler, func()) {
	t.Helper()

	store, cleanupStore := testAuthIntegrationStore(t, ctx)
	authService, err := auth.NewService(auth.Config{
		SuperuserEmail:    "admin@example.com",
		SuperuserPassword: "secret-password",
		SessionTTL:        time.Hour,
		SessionSecret:     authIntegrationSessionSecret(),
		SecureCookies:     false,
		WebAppURL:         "http://localhost:5173",
	}, store)
	if err != nil {
		cleanupStore()
		t.Fatalf("NewService returned error: %v", err)
	}
	if err := authService.EnsureBootstrapAdmin(ctx); err != nil {
		cleanupStore()
		t.Fatalf("EnsureBootstrapAdmin returned error: %v", err)
	}

	handler := Handler(deps.Dependencies{
		Config: config.Config{
			HTTPAddr: ":9090",
		},
		Storage: store,
		Secrets: authIntegrationSecretManager(t),
		Auth:    authService,
	})

	return handler, cleanupStore
}

func testAuthIntegrationStore(t *testing.T, ctx context.Context) (*storage.Store, func()) {
	t.Helper()

	databaseURL := testdb.URL(t, ctx)
	migrationDir, err := filepath.Abs("../../../../packages/storage/migrations")
	if err != nil {
		t.Fatalf("resolve migration dir: %v", err)
	}
	migrateAuthIntegrationOnce.Do(func() {
		migrateAuthIntegrationErr = testdb.MigrateIfNeeded(t, ctx, databaseURL, "auth-integration", func() error {
			return storage.RunMigrations(ctx, databaseURL, "file://"+migrationDir)
		})
	})
	if migrateAuthIntegrationErr != nil {
		t.Fatal(testdb.MigrationTimeoutError(migrateAuthIntegrationErr))
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
	if err := storage.PrepareTestStore(ctx, store); err != nil {
		pool.Close()
		t.Fatalf("PrepareTestStore returned error: %v", err)
	}

	return store, pool.Close
}

func authIntegrationSessionSecret() []byte {
	return authIntegrationBytes32("test-session-secret-key-32b!!!")
}

func authIntegrationSecretManager(t *testing.T) secrets.Manager {
	t.Helper()

	manager, err := secrets.NewStaticKeyManager("local-dev", authIntegrationBytes32("encryption-key-32-bytes-long!!"))
	if err != nil {
		t.Fatalf("NewStaticKeyManager returned error: %v", err)
	}
	return manager
}

func authIntegrationBytes32(value string) []byte {
	raw := []byte(value)
	if len(raw) >= 32 {
		return raw[:32]
	}
	padded := make([]byte, 32)
	copy(padded, raw)
	return padded
}
