package authhttp

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/auth"
	"github.com/ekkuleivonen/relic/packages/storage"
)

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type sessionUserResponse struct {
	ID          string     `json:"id"`
	Email       string     `json:"email"`
	DisplayName string     `json:"display_name,omitempty"`
	Role        auth.Role  `json:"role"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
	DisabledAt  *time.Time `json:"disabled_at,omitempty"`
}

type sessionResponse struct {
	User sessionUserResponse `json:"user"`
}

func RegisterRawHandlers(mux *http.ServeMux, dependencies deps.Dependencies) {
	mux.HandleFunc("POST /api/auth/login", func(w http.ResponseWriter, r *http.Request) {
		handleLogin(w, r, dependencies)
	})
	mux.HandleFunc("POST /api/auth/logout", func(w http.ResponseWriter, r *http.Request) {
		handleLogout(w, r, dependencies)
	})
	mux.HandleFunc("GET /api/auth/oidc/start", func(w http.ResponseWriter, r *http.Request) {
		handleOIDCStart(w, r, dependencies)
	})
	mux.HandleFunc("GET /api/auth/oidc/callback", func(w http.ResponseWriter, r *http.Request) {
		handleOIDCCallback(w, r, dependencies)
	})
}

func handleLogin(w http.ResponseWriter, r *http.Request, dependencies deps.Dependencies) {
	if dependencies.Auth == nil {
		writeJSONError(w, http.StatusServiceUnavailable, "Authentication is not configured.")
		return
	}

	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "Invalid request body.")
		return
	}

	var payload loginRequest
	if err := json.Unmarshal(body, &payload); err != nil {
		writeJSONError(w, http.StatusBadRequest, "Invalid request body.")
		return
	}

	principal, token, err := dependencies.Auth.Login(r.Context(), payload.Email, payload.Password)
	if err != nil {
		switch err {
		case auth.ErrInvalidCredentials, auth.ErrPasswordNotSet, auth.ErrUserDisabled:
			writeJSONError(w, http.StatusUnauthorized, "Invalid email or password.")
		default:
			writeJSONError(w, http.StatusInternalServerError, "Login failed.")
		}
		return
	}

	user, err := dependencies.Auth.GetUser(r.Context(), principal.ID)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "Login failed.")
		return
	}

	cfg := authConfig(dependencies)
	setSessionCookie(w, cfg, token)
	writeJSON(w, http.StatusOK, sessionResponse{User: userResponseFromStorage(user)})
}

func handleLogout(w http.ResponseWriter, r *http.Request, dependencies deps.Dependencies) {
	if dependencies.Auth == nil {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	_ = dependencies.Auth.Logout(r.Context(), sessionTokenFromRequest(r))
	clearSessionCookie(w, authConfig(dependencies))
	w.WriteHeader(http.StatusNoContent)
}

func handleOIDCStart(w http.ResponseWriter, r *http.Request, dependencies deps.Dependencies) {
	if dependencies.Auth == nil || !dependencies.Auth.OIDCEnabled() {
		writeJSONError(w, http.StatusServiceUnavailable, "OIDC is not configured.")
		return
	}

	url, signedState, expiresAt, err := dependencies.Auth.OIDCStartURL()
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "Failed to start OIDC login.")
		return
	}

	setOIDCStateCookie(w, authConfig(dependencies), signedState, expiresAt)
	http.Redirect(w, r, url, http.StatusFound)
}

func handleOIDCCallback(w http.ResponseWriter, r *http.Request, dependencies deps.Dependencies) {
	if dependencies.Auth == nil || !dependencies.Auth.OIDCEnabled() {
		writeJSONError(w, http.StatusServiceUnavailable, "OIDC is not configured.")
		return
	}

	code := strings.TrimSpace(r.URL.Query().Get("code"))
	if code == "" {
		writeJSONError(w, http.StatusBadRequest, "Missing authorization code.")
		return
	}

	signedState := oidcStateFromRequest(r)
	clearOIDCStateCookie(w, authConfig(dependencies))

	_, token, err := dependencies.Auth.OIDCCallback(r.Context(), code, signedState)
	if err != nil {
		switch err {
		case auth.ErrInvalidCredentials, auth.ErrUserDisabled, auth.ErrOIDCStateInvalid:
			writeJSONError(w, http.StatusUnauthorized, "OIDC login failed.")
		default:
			writeJSONError(w, http.StatusInternalServerError, "OIDC login failed.")
		}
		return
	}

	setSessionCookie(w, authConfig(dependencies), token)
	http.Redirect(w, r, dependencies.Auth.Config().WebAppURL, http.StatusFound)
}

func userResponseFromStorage(user storage.User) sessionUserResponse {
	return sessionUserResponse{
		ID:          user.ID,
		Email:       user.Email,
		DisplayName: user.DisplayName,
		Role:        auth.Role(user.Role),
		CreatedAt:   user.CreatedAt,
		UpdatedAt:   user.UpdatedAt,
		DisabledAt:  user.DisabledAt,
	}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
