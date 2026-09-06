package authhttp

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/packages/auth"
)

func setSessionCookie(w http.ResponseWriter, cfg auth.Config, token auth.SessionToken) {
	http.SetCookie(w, &http.Cookie{
		Name:     auth.SessionCookieName,
		Value:    token.Value,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   cfg.SecureCookies,
		Expires:  token.ExpiresAt,
		MaxAge:   int(time.Until(token.ExpiresAt).Seconds()),
	})
}

func clearSessionCookie(w http.ResponseWriter, cfg auth.Config) {
	http.SetCookie(w, &http.Cookie{
		Name:     auth.SessionCookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   cfg.SecureCookies,
		MaxAge:   -1,
	})
}

func setOIDCStateCookie(w http.ResponseWriter, cfg auth.Config, value string, expiresAt time.Time) {
	http.SetCookie(w, &http.Cookie{
		Name:     auth.OIDCStateCookieName,
		Value:    value,
		Path:     "/api/auth/oidc",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   cfg.SecureCookies,
		Expires:  expiresAt,
		MaxAge:   int(time.Until(expiresAt).Seconds()),
	})
}

func clearOIDCStateCookie(w http.ResponseWriter, cfg auth.Config) {
	http.SetCookie(w, &http.Cookie{
		Name:     auth.OIDCStateCookieName,
		Value:    "",
		Path:     "/api/auth/oidc",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   cfg.SecureCookies,
		MaxAge:   -1,
	})
}

func sessionTokenFromRequest(r *http.Request) string {
	if cookie, err := r.Cookie(auth.SessionCookieName); err == nil {
		return cookie.Value
	}
	return ""
}

func oidcStateFromRequest(r *http.Request) string {
	if cookie, err := r.Cookie(auth.OIDCStateCookieName); err == nil {
		return cookie.Value
	}
	return ""
}

func authConfig(dependencies deps.Dependencies) auth.Config {
	if dependencies.Auth == nil {
		return auth.Config{}
	}
	return dependencies.Auth.Config()
}

func writeJSONError(w http.ResponseWriter, status int, detail string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"title":  http.StatusText(status),
		"status": http.StatusText(status),
		"detail": detail,
	})
}
