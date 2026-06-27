package config

import (
	"bufio"
	"encoding/base64"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"golang.org/x/crypto/chacha20poly1305"
)

const (
	defaultHTTPAddr    = ":8080"
	defaultLogLevel    = "info"
	defaultSessionTTL  = 168 * time.Hour
	defaultOIDCRedirect = "http://localhost:8080/api/auth/oidc/callback"
	defaultWebAppURL    = "http://localhost:5173"
)

type Config struct {
	HTTPAddr            string
	DatabaseURL         string
	SuperuserEmail      string
	SuperuserPassword   string
	SessionSecret       []byte
	SessionTTL          time.Duration
	OIDCIssuerURL       string
	OIDCClientID        string
	OIDCClientSecret    string
	OIDCRedirectURL     string
	WebAppURL           string
	EncryptionKeyID     string
	EncryptionKey       []byte
	LogLevel            string
}

type lookupFunc func(string) (string, bool)

func Load() (Config, error) {
	fileEnv, err := loadDotEnv(".env")
	if err != nil {
		return Config{}, err
	}

	return LoadFromLookup(func(key string) (string, bool) {
		if value, ok := os.LookupEnv(key); ok {
			return value, true
		}

		value, ok := fileEnv[key]
		return value, ok
	})
}

func LoadFromLookup(lookup lookupFunc) (Config, error) {
	encryptionKeyBase64 := stringEnv(lookup, "ENCRYPTION_KEY_BASE64", "")
	encryptionKey, err := encryptionKeyEnv(encryptionKeyBase64)
	if err != nil {
		return Config{}, err
	}

	sessionTTL, err := durationEnv(lookup, "SESSION_TTL", defaultSessionTTL)
	if err != nil {
		return Config{}, err
	}

	sessionSecretBase64 := stringEnv(lookup, "SESSION_SECRET_BASE64", "")
	var sessionSecret []byte
	if sessionSecretBase64 != "" {
		sessionSecret, err = sessionSecretEnv(sessionSecretBase64)
		if err != nil {
			return Config{}, err
		}
	}

	cfg := Config{
		HTTPAddr:          stringEnv(lookup, "HTTP_ADDR", defaultHTTPAddr),
		DatabaseURL:       stringEnv(lookup, "DATABASE_URL", ""),
		SuperuserEmail:    stringEnv(lookup, "SUPERUSER_EMAIL", ""),
		SuperuserPassword: stringEnv(lookup, "SUPERUSER_PASSWORD", ""),
		SessionSecret:     sessionSecret,
		SessionTTL:        sessionTTL,
		OIDCIssuerURL:     stringEnv(lookup, "OIDC_ISSUER_URL", ""),
		OIDCClientID:      stringEnv(lookup, "OIDC_CLIENT_ID", ""),
		OIDCClientSecret:  stringEnv(lookup, "OIDC_CLIENT_SECRET", ""),
		OIDCRedirectURL:   stringEnv(lookup, "OIDC_REDIRECT_URL", defaultOIDCRedirect),
		WebAppURL:         stringEnv(lookup, "WEB_APP_URL", defaultWebAppURL),
		EncryptionKeyID:   stringEnv(lookup, "ENCRYPTION_KEY_ID", ""),
		EncryptionKey:     encryptionKey,
		LogLevel:          stringEnv(lookup, "LOG_LEVEL", defaultLogLevel),
	}

	if cfg.DatabaseURL == "" {
		return Config{}, errors.New("DATABASE_URL is required")
	}
	if cfg.EncryptionKeyID == "" {
		return Config{}, errors.New("ENCRYPTION_KEY_ID is required")
	}
	if cfg.SuperuserEmail == "" {
		return Config{}, errors.New("SUPERUSER_EMAIL is required")
	}
	if len(cfg.SessionSecret) == 0 {
		return Config{}, errors.New("SESSION_SECRET_BASE64 is required")
	}
	if cfg.SuperuserPassword == "" {
		return Config{}, errors.New("SUPERUSER_PASSWORD is required")
	}

	oidcValues := []string{cfg.OIDCIssuerURL, cfg.OIDCClientID, cfg.OIDCClientSecret}
	oidcSet := 0
	for _, value := range oidcValues {
		if value != "" {
			oidcSet++
		}
	}
	if oidcSet > 0 && oidcSet < len(oidcValues) {
		return Config{}, errors.New("OIDC_ISSUER_URL, OIDC_CLIENT_ID, and OIDC_CLIENT_SECRET must all be set together")
	}

	return cfg, nil
}

func (c Config) SecureCookies() bool {
	return !strings.Contains(c.HTTPAddr, "localhost") && !strings.HasSuffix(c.HTTPAddr, ":8080")
}

func stringEnv(lookup lookupFunc, key string, fallback string) string {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback
	}

	return value
}

func durationEnv(lookup lookupFunc, key string, fallback time.Duration) (time.Duration, error) {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback, nil
	}

	parsed, err := time.ParseDuration(value)
	if err != nil {
		return 0, fmt.Errorf("parse %s: %w", key, err)
	}
	if parsed <= 0 {
		return 0, fmt.Errorf("parse %s: duration must be positive", key)
	}

	return parsed, nil
}

func encryptionKeyEnv(value string) ([]byte, error) {
	if value == "" {
		return nil, errors.New("ENCRYPTION_KEY_BASE64 is required")
	}

	decoded, err := base64.StdEncoding.DecodeString(value)
	if err != nil {
		return nil, fmt.Errorf("parse ENCRYPTION_KEY_BASE64: %w", err)
	}
	if len(decoded) != chacha20poly1305.KeySize {
		return nil, fmt.Errorf("parse ENCRYPTION_KEY_BASE64: decoded key is %d bytes, want %d", len(decoded), chacha20poly1305.KeySize)
	}

	return decoded, nil
}

func sessionSecretEnv(value string) ([]byte, error) {
	decoded, err := base64.StdEncoding.DecodeString(value)
	if err != nil {
		return nil, fmt.Errorf("parse SESSION_SECRET_BASE64: %w", err)
	}
	if len(decoded) != chacha20poly1305.KeySize {
		return nil, fmt.Errorf("parse SESSION_SECRET_BASE64: decoded key is %d bytes, want %d", len(decoded), chacha20poly1305.KeySize)
	}

	return decoded, nil
}

func loadDotEnv(path string) (map[string]string, error) {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return map[string]string{}, nil
		}

		return nil, err
	}
	defer file.Close()

	values := map[string]string{}
	scanner := bufio.NewScanner(file)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return nil, fmt.Errorf("parse %s: invalid line %q", path, line)
		}

		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)

		if key == "" {
			return nil, fmt.Errorf("parse %s: empty key", path)
		}

		values[key] = value
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return values, nil
}
