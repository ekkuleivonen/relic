package httpserver

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestListSettingsRequiresAuth(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	req := httptest.NewRequest(http.MethodGet, "/api/settings", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusUnauthorized, rec.Body.String())
	}
}

func TestListSettingsReturnsSeededKeys(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	req := httptest.NewRequest(http.MethodGet, "/api/settings", nil)
	req.AddCookie(adminCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var body struct {
		Items []struct {
			Key   string `json:"key"`
			Value string `json:"value"`
		} `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) == 0 {
		t.Fatal("expected seeded settings items")
	}
}

func TestPatchSettingRequiresAdmin(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

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

	req := httptest.NewRequest(http.MethodPatch, "/api/settings/WORKER_RUNNER_POLL_INTERVAL", strings.NewReader(`{"value":"3s"}`))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(memberCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusForbidden, rec.Body.String())
	}
}

func TestPatchSettingAdminUpdatesValue(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	req := httptest.NewRequest(http.MethodPatch, "/api/settings/WORKER_RUNNER_POLL_INTERVAL", strings.NewReader(`{"value":"3s"}`))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(adminCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusOK, rec.Body.String())
	}

	var body struct {
		Key       string  `json:"key"`
		Value     string  `json:"value"`
		UpdatedBy *string `json:"updated_by"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body.Key != "WORKER_RUNNER_POLL_INTERVAL" {
		t.Fatalf("Key = %q, want WORKER_RUNNER_POLL_INTERVAL", body.Key)
	}
	if body.Value != "3s" {
		t.Fatalf("Value = %q, want 3s", body.Value)
	}
	if body.UpdatedBy == nil || *body.UpdatedBy == "" {
		t.Fatalf("UpdatedBy = %#v, want admin user id", body.UpdatedBy)
	}
}

func TestPatchSettingRejectsUnknownKey(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	req := httptest.NewRequest(http.MethodPatch, "/api/settings/NOT_A_SETTING", strings.NewReader(`{"value":"true"}`))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(adminCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusUnprocessableEntity, rec.Body.String())
	}
}

func TestPatchSettingRejectsInvalidDuration(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	req := httptest.NewRequest(http.MethodPatch, "/api/settings/WORKER_RUNNER_POLL_INTERVAL", strings.NewReader(`{"value":"not-a-duration"}`))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(adminCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusUnprocessableEntity, rec.Body.String())
	}
}
