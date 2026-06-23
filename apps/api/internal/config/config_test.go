package config

import "testing"

func TestLoadFromLookupDefaults(t *testing.T) {
	cfg, err := LoadFromLookup(mapLookup(nil))
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
		"HTTP_ADDR":      ":9090",
		"DATABASE_URL":   "postgres://relic:relic@localhost:5432/relic",
		"AUTH_ENABLED":   "false",
		"ENCRYPTION_KEY": "dev-key",
		"LOG_LEVEL":      "debug",
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

	if cfg.EncryptionKey != "dev-key" {
		t.Fatalf("EncryptionKey = %q, want dev-key", cfg.EncryptionKey)
	}

	if cfg.LogLevel != "debug" {
		t.Fatalf("LogLevel = %q, want debug", cfg.LogLevel)
	}
}

func TestLoadFromLookupRejectsAuthEnabled(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"AUTH_ENABLED": "true",
	}))
	if err == nil {
		t.Fatal("LoadFromLookup returned nil error")
	}
}

func TestLoadFromLookupRejectsInvalidBool(t *testing.T) {
	_, err := LoadFromLookup(mapLookup(map[string]string{
		"AUTH_ENABLED": "sometimes",
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
