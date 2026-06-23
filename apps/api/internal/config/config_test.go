package config

import (
	"encoding/base64"
	"testing"
)

func TestLoadFromLookupDefaults(t *testing.T) {
	cfg, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://relic:relic@localhost:5432/relic",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
	}))
	if err != nil {
		t.Fatalf("LoadFromLookup returned error: %v", err)
	}

	if cfg.HTTPAddr != ":8080" {
		t.Fatalf("HTTPAddr = %q, want :8080", cfg.HTTPAddr)
	}

	if cfg.AuthEnabled {
		t.Fatal("AuthEnabled = true, want false")
	}

	if cfg.LogLevel != "info" {
		t.Fatalf("LogLevel = %q, want info", cfg.LogLevel)
	}
}

func TestLoadFromLookupOverrides(t *testing.T) {
	cfg, err := LoadFromLookup(mapLookup(map[string]string{
		"HTTP_ADDR":             ":9090",
		"DATABASE_URL":          "postgres://relic:relic@localhost:5432/relic",
		"AUTH_ENABLED":          "false",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
		"LOG_LEVEL":             "debug",
	}))
	if err != nil {
		t.Fatalf("LoadFromLookup returned error: %v", err)
	}

	if cfg.HTTPAddr != ":9090" {
		t.Fatalf("HTTPAddr = %q, want :9090", cfg.HTTPAddr)
	}

	if cfg.DatabaseURL == "" {
		t.Fatal("DatabaseURL is empty")
	}

	if cfg.EncryptionKeyID != "local-dev" {
		t.Fatalf("EncryptionKeyID = %q, want local-dev", cfg.EncryptionKeyID)
	}

	if len(cfg.EncryptionKey) != 32 {
		t.Fatalf("EncryptionKey length = %d, want 32", len(cfg.EncryptionKey))
	}

	if cfg.LogLevel != "debug" {
		t.Fatalf("LogLevel = %q, want debug", cfg.LogLevel)
	}
}

func TestLoadFromLookupRejectsAuthEnabled(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"AUTH_ENABLED":          "true",
		"DATABASE_URL":          "postgres://relic:relic@localhost:5432/relic",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRejectsInvalidBool(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"AUTH_ENABLED":          "sometimes",
		"DATABASE_URL":          "postgres://relic:relic@localhost:5432/relic",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRequiresDatabaseURL(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRequiresEncryptionKeyID(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://relic:relic@localhost:5432/relic",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRequiresEncryptionKey(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":      "postgres://relic:relic@localhost:5432/relic",
		"ENCRYPTION_KEY_ID": "local-dev",
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRejectsInvalidEncryptionKeyBase64(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://relic:relic@localhost:5432/relic",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": "not-base64",
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRejectsWrongLengthEncryptionKey(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://relic:relic@localhost:5432/relic",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": base64.StdEncoding.EncodeToString([]byte("too-short")),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func mapLookup(values map[string]string) lookupFunc {
	return func(key string) (string, bool) {
		value, ok := values[key]
		return value, ok
	}
}

func testEncryptionKeyBase64() string {
	return base64.StdEncoding.EncodeToString(make([]byte, 32))
}
