package auth

import (
	"testing"
	"time"
)

func TestSessionManagerNewSessionToken(t *testing.T) {
	manager := NewSessionManager()

	token, err := manager.NewSessionToken(time.Hour)
	if err != nil {
		t.Fatalf("NewSessionToken returned error: %v", err)
	}
	if token.Value == "" {
		t.Fatal("session token value is empty")
	}
	if len(token.TokenHash) != 32 {
		t.Fatalf("token hash length = %d, want 32", len(token.TokenHash))
	}
	if !token.ExpiresAt.After(time.Now().UTC()) {
		t.Fatal("expires_at is not in the future")
	}

	second := HashSessionToken(token.Value)
	if string(second) != string(token.TokenHash) {
		t.Fatal("hash session token is not deterministic")
	}
}

func TestOIDCConfigEnabled(t *testing.T) {
	if (OIDCConfig{}).Enabled() {
		t.Fatal("empty OIDC config should not be enabled")
	}

	cfg := OIDCConfig{
		IssuerURL:    "https://issuer.example",
		ClientID:     "client",
		ClientSecret: "secret",
		RedirectURL:  "http://localhost:8080/callback",
	}
	if !cfg.Enabled() {
		t.Fatal("complete OIDC config should be enabled")
	}
}
