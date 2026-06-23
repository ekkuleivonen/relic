package config

import (
	"bufio"
	"encoding/base64"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"

	"golang.org/x/crypto/chacha20poly1305"
)

const (
	defaultHTTPAddr = ":8080"
	defaultLogLevel = "info"
)

type Config struct {
	HTTPAddr        string
	DatabaseURL     string
	AuthEnabled     bool
	EncryptionKeyID string
	EncryptionKey   []byte
	LogLevel        string
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
	authEnabled, err := boolEnv(lookup, "AUTH_ENABLED", false)
	if err != nil {
		return Config{}, err
	}

	if authEnabled {
		return Config{}, errors.New("AUTH_ENABLED=true is not implemented yet")
	}

	encryptionKeyBase64 := stringEnv(lookup, "ENCRYPTION_KEY_BASE64", "")
	encryptionKey, err := encryptionKeyEnv(encryptionKeyBase64)
	if err != nil {
		return Config{}, err
	}

	cfg := Config{
		HTTPAddr:        stringEnv(lookup, "HTTP_ADDR", defaultHTTPAddr),
		DatabaseURL:     stringEnv(lookup, "DATABASE_URL", ""),
		AuthEnabled:     authEnabled,
		EncryptionKeyID: stringEnv(lookup, "ENCRYPTION_KEY_ID", ""),
		EncryptionKey:   encryptionKey,
		LogLevel:        stringEnv(lookup, "LOG_LEVEL", defaultLogLevel),
	}

	if cfg.DatabaseURL == "" {
		return Config{}, errors.New("DATABASE_URL is required")
	}
	if cfg.EncryptionKeyID == "" {
		return Config{}, errors.New("ENCRYPTION_KEY_ID is required")
	}

	return cfg, nil
}

func stringEnv(lookup lookupFunc, key string, fallback string) string {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback
	}

	return value
}

func boolEnv(lookup lookupFunc, key string, fallback bool) (bool, error) {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback, nil
	}

	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return false, fmt.Errorf("parse %s: %w", key, err)
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
