package config

import (
	"encoding/base64"
	"testing"
)

func TestLoadFromLookupDefaults(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupOverrides(t *testing.T) {
	cfg, err := LoadFromLookup(mapLookup(mergeEnv(map[string]string{
		"HTTP_ADDR":    ":9090",
		"DATABASE_URL": "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"LOG_LEVEL":    "debug",
	})))
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

func TestLoadFromLookupRequiresAuthConfig(t *testing.T) {
	cfg, err := LoadFromLookup(mapLookup(mergeEnv(map[string]string{
		"DATABASE_URL": "postgres://pithosys:pithosys@localhost:5432/pithosys",
	})))
	if err != nil {
		t.Fatalf("LoadFromLookup returned error: %v", err)
	}
	if cfg.SuperuserEmail != "admin@example.com" {
		t.Fatalf("SuperuserEmail = %q, want admin@example.com", cfg.SuperuserEmail)
	}
}

func TestLoadFromLookupRejectsPartialOIDCConfig(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(mergeEnv(map[string]string{
		"DATABASE_URL":    "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"OIDC_ISSUER_URL": "https://issuer.example",
	})))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRejectsMissingSessionSecret(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
		"SUPERUSER_EMAIL":       "admin@example.com",
		"SUPERUSER_PASSWORD":    "secret-password",
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
		"DATABASE_URL":          "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRequiresEncryptionKey(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":      "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"ENCRYPTION_KEY_ID": "local-dev",
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRejectsInvalidEncryptionKeyBase64(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": "not-base64",
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRejectsWrongLengthEncryptionKey(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"DATABASE_URL":          "postgres://pithosys:pithosys@localhost:5432/pithosys",
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": base64.StdEncoding.EncodeToString([]byte("too-short")),
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func mergeEnv(values map[string]string) map[string]string {
	merged := map[string]string{
		"ENCRYPTION_KEY_ID":     "local-dev",
		"ENCRYPTION_KEY_BASE64": testEncryptionKeyBase64(),
		"SUPERUSER_EMAIL":       "admin@example.com",
		"SUPERUSER_PASSWORD":    "secret-password",
		"SESSION_SECRET_BASE64": testSessionSecretBase64(),
	}
	for key, value := range values {
		merged[key] = value
	}
	return merged
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

func testSessionSecretBase64() string {
	return base64.StdEncoding.EncodeToString(make([]byte, 32))
}
