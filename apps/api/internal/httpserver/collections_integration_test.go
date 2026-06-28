package httpserver

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestListCollectionsRequiresAuth(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	req := httptest.NewRequest(http.MethodGet, "/api/collections", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusUnauthorized, rec.Body.String())
	}
}

func TestCreateCollectionRequiresAdmin(t *testing.T) {
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

	req := httptest.NewRequest(http.MethodPost, "/api/collections", strings.NewReader(`{"name":"Finance","query":"FROM objects WHERE key = 'finance/report.pdf'"}`))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(memberCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusForbidden, rec.Body.String())
	}
}

func TestCreateCollectionRejectsInvalidQuery(t *testing.T) {
	ctx := context.Background()
	handler, cleanup := testAuthIntegrationHandler(t, ctx)
	defer cleanup()

	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	req := httptest.NewRequest(http.MethodPost, "/api/collections", strings.NewReader(`{"name":"Bad query","query":"FROM buckets"}`))
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(adminCookie)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d; body = %s", rec.Code, http.StatusBadRequest, rec.Body.String())
	}
}

func TestCollectionCRUDAndObjects(t *testing.T) {
	ctx := context.Background()
	handler, store, cleanup := testAuthIntegrationHandlerWithStore(t, ctx)
	defer cleanup()

	objectID := createIntegrationTestObject(t, ctx, store)
	adminCookie := loginIntegrationUser(t, handler, "admin@example.com", "secret-password")

	patchReq := httptest.NewRequest(http.MethodPatch, "/api/objects/"+objectID+"/attributes", strings.NewReader(`{"set":{"user.owner":"finance"}}`))
	patchReq.Header.Set("Content-Type", "application/json")
	patchReq.AddCookie(adminCookie)
	patchRec := httptest.NewRecorder()
	handler.ServeHTTP(patchRec, patchReq)
	if patchRec.Code != http.StatusOK {
		t.Fatalf("patch object status = %d, want %d; body = %s", patchRec.Code, http.StatusOK, patchRec.Body.String())
	}

	createReq := httptest.NewRequest(http.MethodPost, "/api/collections", strings.NewReader(`{"name":"Finance owners","description":"Owned by finance","query":"FROM objects WHERE attr('user.owner') = 'finance'"}`))
	createReq.Header.Set("Content-Type", "application/json")
	createReq.AddCookie(adminCookie)
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusOK {
		t.Fatalf("create collection status = %d, want %d; body = %s", createRec.Code, http.StatusOK, createRec.Body.String())
	}

	var created struct {
		ID     string `json:"id"`
		Name   string `json:"name"`
		Query  string `json:"query"`
		Status string `json:"status"`
	}
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	if created.ID == "" {
		t.Fatal("expected collection id")
	}
	if created.Status != "valid" {
		t.Fatalf("Status = %q, want valid", created.Status)
	}

	memberCookie := loginIntegrationUser(t, handler, "member@example.com", "member-password")

	listReq := httptest.NewRequest(http.MethodGet, "/api/collections", nil)
	listReq.AddCookie(memberCookie)
	listRec := httptest.NewRecorder()
	handler.ServeHTTP(listRec, listReq)
	if listRec.Code != http.StatusOK {
		t.Fatalf("list collections status = %d, want %d; body = %s", listRec.Code, http.StatusOK, listRec.Body.String())
	}

	getReq := httptest.NewRequest(http.MethodGet, "/api/collections/"+created.ID, nil)
	getReq.AddCookie(memberCookie)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusOK {
		t.Fatalf("get collection status = %d, want %d; body = %s", getRec.Code, http.StatusOK, getRec.Body.String())
	}

	objectsReq := httptest.NewRequest(http.MethodGet, "/api/collections/"+created.ID+"/objects", nil)
	objectsReq.AddCookie(memberCookie)
	objectsRec := httptest.NewRecorder()
	handler.ServeHTTP(objectsRec, objectsReq)
	if objectsRec.Code != http.StatusOK {
		t.Fatalf("list collection objects status = %d, want %d; body = %s", objectsRec.Code, http.StatusOK, objectsRec.Body.String())
	}

	var objectsBody struct {
		Objects []struct {
			ID string `json:"id"`
		} `json:"objects"`
	}
	if err := json.Unmarshal(objectsRec.Body.Bytes(), &objectsBody); err != nil {
		t.Fatalf("decode objects response: %v", err)
	}
	if len(objectsBody.Objects) != 1 {
		t.Fatalf("object count = %d, want 1", len(objectsBody.Objects))
	}
	if objectsBody.Objects[0].ID != objectID {
		t.Fatalf("object id = %q, want %q", objectsBody.Objects[0].ID, objectID)
	}

	deleteReq := httptest.NewRequest(http.MethodDelete, "/api/collections/"+created.ID, nil)
	deleteReq.AddCookie(adminCookie)
	deleteRec := httptest.NewRecorder()
	handler.ServeHTTP(deleteRec, deleteReq)
	if deleteRec.Code != http.StatusOK && deleteRec.Code != http.StatusNoContent {
		t.Fatalf("delete collection status = %d, want 200 or 204; body = %s", deleteRec.Code, deleteRec.Body.String())
	}

	getAfterDeleteReq := httptest.NewRequest(http.MethodGet, "/api/collections/"+created.ID, nil)
	getAfterDeleteReq.AddCookie(memberCookie)
	getAfterDeleteRec := httptest.NewRecorder()
	handler.ServeHTTP(getAfterDeleteRec, getAfterDeleteReq)
	if getAfterDeleteRec.Code != http.StatusNotFound {
		t.Fatalf("get after delete status = %d, want %d; body = %s", getAfterDeleteRec.Code, http.StatusNotFound, getAfterDeleteRec.Body.String())
	}
}
