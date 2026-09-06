package httpserver

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/elei-io/pithosys/apps/api/internal/config"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/packages/auth"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
)

func TestPatchObjectAttributesRequiresAuth(t *testing.T) {
	ctx := context.Background()
	handler, store, cleanup := testAuthIntegrationHandlerWithStore(t, ctx)
	defer cleanup()

	objectID := createIntegrationTestObject(t, ctx, store)

	req := httptest.NewRequest(http.MethodPatch, "/api/objects/"+objectID+"/attributes", strings.NewReader(`{"set":{"user.owner":"finance"}}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusUnauthorized, rec.Body.String())
	}
}

func TestPatchObjectAttributesRequiresAdmin(t *testing.T) {
	ctx := context.Background()
	handler, store, cleanup := testAuthIntegrationHandlerWithStore(t, ctx)
	defer cleanup()

	objectID := createIntegrationTestObject(t, ctx, store)
	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	createUserReq := httptest.NewRequest(http.MethodPost, "/api/users", strings.NewReader(`{"email":"member@example.com","password":"member-password","role":"user"}`))
	createUserReq.Header.Set("Content-Type", "application/json")
	createUserReq.AddCookie(adminCookie)
	createUserRec := httptest.NewRecorder()
	handler.ServeHTTP(createUserRec, createUserReq)
	if createUserRec.Code != http.StatusOK {
		t.Fatalf("create user status = %d, want %d; body = %s", createUserRec.Code, http.StatusOK, createUserRec.Body.String())
	}

	memberCookie := loginIntegrationUser(t, handler, "member@example.com", "member-password")

	req := httptest.NewRequest(http.MethodPatch, "/api/objects/"+objectID+"/attributes", strings.NewReader(`{"set":{"user.owner":"finance"}}`))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(memberCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusForbidden, rec.Body.String())
	}
}

func TestPatchObjectAttributesAdminCanSetAndDelete(t *testing.T) {
	ctx := context.Background()
	handler, store, cleanup := testAuthIntegrationHandlerWithStore(t, ctx)
	defer cleanup()

	objectID := createIntegrationTestObject(t, ctx, store)
	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	patchReq := httptest.NewRequest(http.MethodPatch, "/api/objects/"+objectID+"/attributes", strings.NewReader(`{"set":{"user.owner":"finance","user.review.status":"approved"}}`))
	patchReq.Header.Set("Content-Type", "application/json")
	patchReq.AddCookie(adminCookie)
	patchRec := httptest.NewRecorder()
	handler.ServeHTTP(patchRec, patchReq)

	if patchRec.Code != http.StatusOK {
		t.Fatalf("patch status = %d, want %d; body = %s", patchRec.Code, http.StatusOK, patchRec.Body.String())
	}

	var patched struct {
		Attributes map[string]any `json:"attributes"`
	}
	if err := json.Unmarshal(patchRec.Body.Bytes(), &patched); err != nil {
		t.Fatalf("decode patch response: %v", err)
	}
	userAttrs, ok := patched.Attributes["user"].(map[string]any)
	if !ok {
		t.Fatalf("user attributes = %#v, want object", patched.Attributes["user"])
	}
	if userAttrs["owner"] != "finance" {
		t.Fatalf("user.owner = %#v, want finance", userAttrs["owner"])
	}
	review, ok := userAttrs["review"].(map[string]any)
	if !ok || review["status"] != "approved" {
		t.Fatalf("user.review.status = %#v, want approved", userAttrs["review"])
	}

	deleteReq := httptest.NewRequest(http.MethodPatch, "/api/objects/"+objectID+"/attributes", strings.NewReader(`{"delete":["user.review.status"]}`))
	deleteReq.Header.Set("Content-Type", "application/json")
	deleteReq.AddCookie(adminCookie)
	deleteRec := httptest.NewRecorder()
	handler.ServeHTTP(deleteRec, deleteReq)

	if deleteRec.Code != http.StatusOK {
		t.Fatalf("delete status = %d, want %d; body = %s", deleteRec.Code, http.StatusOK, deleteRec.Body.String())
	}

	getReq := httptest.NewRequest(http.MethodGet, "/api/objects/"+objectID, nil)
	getReq.AddCookie(adminCookie)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)

	if getRec.Code != http.StatusOK {
		t.Fatalf("get status = %d, want %d; body = %s", getRec.Code, http.StatusOK, getRec.Body.String())
	}

	var got struct {
		Attributes map[string]any `json:"attributes"`
	}
	if err := json.Unmarshal(getRec.Body.Bytes(), &got); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	userAttrs, ok = got.Attributes["user"].(map[string]any)
	if !ok {
		t.Fatalf("user attributes = %#v, want object", got.Attributes["user"])
	}
	if userAttrs["owner"] != "finance" {
		t.Fatalf("user.owner = %#v, want finance", userAttrs["owner"])
	}
	if _, ok := userAttrs["review"]; ok {
		t.Fatalf("user.review should be deleted, got %#v", userAttrs["review"])
	}
}

func testAuthIntegrationHandlerWithStore(t *testing.T, ctx context.Context) (http.Handler, *storage.Store, func()) {
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

	return handler, store, cleanupStore
}

func loginIntegrationUser(t *testing.T, handler http.Handler, email, password string) *http.Cookie {
	t.Helper()

	body, err := json.Marshal(map[string]string{
		"email":    email,
		"password": password,
	})
	if err != nil {
		t.Fatalf("marshal login body: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/auth/login", strings.NewReader(string(body)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("login status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	for _, cookie := range rec.Result().Cookies() {
		if cookie.Name == auth.SessionCookieName {
			return cookie
		}
	}

	t.Fatal("login response did not set session cookie")
	return nil
}

func createIntegrationTestObject(t *testing.T, ctx context.Context, store *storage.Store) string {
	t.Helper()

	bucket, err := store.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
		Name:        "integration-" + time.Now().Format("20060102150405.000000000"),
		Upstream:    storage.BucketUpstreamS3,
		EndpointURL: "https://s3.example.com",
		Region:      "us-east-1",
		BucketName:  "integration-bucket",
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

	seenAt := time.Now().UTC()
	object, err := store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID: bucket.ID,
		Key:      "integration/object.jpg",
		Attributes: storage.ObjectAttributes{
			"upstream": map[string]any{"etag": "\"abc\""},
		},
		SeenAt: &seenAt,
	})
	if err != nil {
		t.Fatalf("UpsertObject returned error: %v", err)
	}

	return object.ID
}
