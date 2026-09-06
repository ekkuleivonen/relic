package auth

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strings"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
	"golang.org/x/oauth2"
)

type OIDCConfig struct {
	IssuerURL    string
	ClientID     string
	ClientSecret string
	RedirectURL  string
}

func (c OIDCConfig) Enabled() bool {
	return c.IssuerURL != "" && c.ClientID != "" && c.ClientSecret != "" && c.RedirectURL != ""
}

type OIDCProvider struct {
	config   OIDCConfig
	provider *oidc.Provider
	verifier *oidc.IDTokenVerifier
	oauth    oauth2.Config
	secret   []byte
}

func NewOIDCProvider(cfg OIDCConfig, sessionSecret []byte) (*OIDCProvider, error) {
	if !cfg.Enabled() {
		return nil, nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	provider, err := oidc.NewProvider(ctx, cfg.IssuerURL)
	if err != nil {
		return nil, fmt.Errorf("create oidc provider: %w", err)
	}

	return &OIDCProvider{
		config:   cfg,
		provider: provider,
		verifier: provider.Verifier(&oidc.Config{ClientID: cfg.ClientID}),
		oauth: oauth2.Config{
			ClientID:     cfg.ClientID,
			ClientSecret: cfg.ClientSecret,
			RedirectURL:  cfg.RedirectURL,
			Endpoint:     provider.Endpoint(),
			Scopes:       []string{oidc.ScopeOpenID, "profile", "email"},
		},
		secret: sessionSecret,
	}, nil
}

func (p *OIDCProvider) Enabled() bool {
	return p != nil
}

func (p *OIDCProvider) AuthCodeURL(state string) string {
	return p.oauth.AuthCodeURL(state, oauth2.AccessTypeOffline)
}

func (p *OIDCProvider) Exchange(ctx context.Context, code string) (*oidc.IDToken, string, string, error) {
	oauthToken, err := p.oauth.Exchange(ctx, code)
	if err != nil {
		return nil, "", "", fmt.Errorf("exchange oidc code: %w", err)
	}

	rawIDToken, ok := oauthToken.Extra("id_token").(string)
	if !ok || rawIDToken == "" {
		return nil, "", "", fmt.Errorf("exchange oidc code: missing id_token")
	}

	idToken, err := p.verifier.Verify(ctx, rawIDToken)
	if err != nil {
		return nil, "", "", fmt.Errorf("verify oidc id token: %w", err)
	}

	var claims struct {
		Email         string `json:"email"`
		EmailVerified bool   `json:"email_verified"`
		Name          string `json:"name"`
	}
	if err := idToken.Claims(&claims); err != nil {
		return nil, "", "", fmt.Errorf("decode oidc claims: %w", err)
	}

	email := strings.TrimSpace(strings.ToLower(claims.Email))
	if email == "" || !claims.EmailVerified {
		return nil, "", "", ErrOIDCEmailMissing
	}

	displayName := strings.TrimSpace(claims.Name)
	return idToken, email, displayName, nil
}

func (p *OIDCProvider) SignState(state string, expiresAt time.Time) (string, error) {
	if p == nil {
		return "", ErrOIDCNotConfigured
	}
	payload := state + "|" + expiresAt.UTC().Format(time.RFC3339Nano)
	mac := hmac.New(sha256.New, p.secret)
	if _, err := mac.Write([]byte(payload)); err != nil {
		return "", fmt.Errorf("sign oidc state: %w", err)
	}
	signature := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	return base64.RawURLEncoding.EncodeToString([]byte(payload + "|" + signature)), nil
}

func (p *OIDCProvider) VerifyState(signed string) (string, error) {
	if p == nil {
		return "", ErrOIDCNotConfigured
	}

	decoded, err := base64.RawURLEncoding.DecodeString(signed)
	if err != nil {
		return "", ErrOIDCStateInvalid
	}

	parts := strings.Split(string(decoded), "|")
	if len(parts) != 3 {
		return "", ErrOIDCStateInvalid
	}

	state := parts[0]
	expiresRaw := parts[1]
	signature := parts[2]

	expiresAt, err := time.Parse(time.RFC3339Nano, expiresRaw)
	if err != nil {
		return "", ErrOIDCStateInvalid
	}
	if !expiresAt.After(time.Now().UTC()) {
		return "", ErrOIDCStateInvalid
	}

	payload := state + "|" + expiresRaw
	mac := hmac.New(sha256.New, p.secret)
	if _, err := mac.Write([]byte(payload)); err != nil {
		return "", ErrOIDCStateInvalid
	}
	expected := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(signature), []byte(expected)) {
		return "", ErrOIDCStateInvalid
	}

	return state, nil
}

func (p *OIDCProvider) VerifyCallbackState(returnedState, signedState string) error {
	expected, err := p.VerifyState(signedState)
	if err != nil {
		return err
	}
	if returnedState == "" || !hmac.Equal([]byte(returnedState), []byte(expected)) {
		return ErrOIDCStateInvalid
	}
	return nil
}
