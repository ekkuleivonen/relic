package middleware

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/auth"
)

func Auth(next http.Handler, dependencies deps.Dependencies) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if isPublicPath(r.URL.Path) {
			next.ServeHTTP(w, r)
			return
		}

		if dependencies.Auth == nil {
			writeServiceUnavailable(w)
			return
		}

		sessionToken := sessionTokenFromRequest(r)
		principal, err := dependencies.Auth.SessionFromToken(r.Context(), sessionToken)
		if err != nil {
			writeUnauthorized(w)
			return
		}

		next.ServeHTTP(w, r.WithContext(auth.WithPrincipal(r.Context(), principal)))
	})
}

func isPublicPath(path string) bool {
	switch path {
	case "/api/healthz", "/api/openapi", "/api/openapi.json", "/api/docs", "/api/schemas":
		return true
	}

	if strings.HasPrefix(path, "/api/auth/login") ||
		strings.HasPrefix(path, "/api/auth/logout") ||
		strings.HasPrefix(path, "/api/auth/config") ||
		strings.HasPrefix(path, "/api/auth/oidc/") {
		return true
	}

	return false
}

func sessionTokenFromRequest(r *http.Request) string {
	if cookie, err := r.Cookie(auth.SessionCookieName); err == nil {
		return cookie.Value
	}
	return ""
}

func writeUnauthorized(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusUnauthorized)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"title":  "Unauthorized",
		"status": "401",
		"detail": "Authentication is required.",
	})
}

func PrincipalFromRequest(r *http.Request) (auth.Principal, bool) {
	return auth.PrincipalFromContext(r.Context())
}

func RequireAdmin(w http.ResponseWriter, r *http.Request) (auth.Principal, bool) {
	principal, ok := auth.PrincipalFromContext(r.Context())
	if !ok {
		writeUnauthorized(w)
		return auth.Principal{}, false
	}
	if err := auth.RequireAdmin(principal); err != nil {
		writeForbidden(w)
		return auth.Principal{}, false
	}
	return principal, true
}

func RequireAdminContext(ctx context.Context) (auth.Principal, error) {
	principal, ok := auth.PrincipalFromContext(ctx)
	if !ok {
		return auth.Principal{}, huma.Error401Unauthorized("Authentication is required.")
	}
	if err := auth.RequireAdmin(principal); err != nil {
		return auth.Principal{}, huma.Error403Forbidden("Admin access is required.")
	}
	return principal, nil
}

func writeServiceUnavailable(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusServiceUnavailable)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"title":  "Service Unavailable",
		"status": "503",
		"detail": "Authentication is not configured.",
	})
}

func writeForbidden(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusForbidden)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"title":  "Forbidden",
		"status": "403",
		"detail": "You do not have permission to perform this action.",
	})
}
