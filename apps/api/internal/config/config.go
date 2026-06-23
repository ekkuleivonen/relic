package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
)

const (
	defaultHTTPAddr = ":8080"
	defaultLogLevel = "info"
)

type Config struct {
	HTTPAddr      string
	DatabaseURL   string
	AuthEnabled   bool
	EncryptionKey string
	LogLevel      string
}

type lookupFunc func(string) (string, bool)

func Load() (Config, error) {
	return LoadFromLookup(os.LookupEnv)
}

func LoadFromLookup(lookup lookupFunc) (Config, error) {
	authEnabled, err := boolEnv(lookup, "AUTH_ENABLED", false)
	if err != nil {
		return Config{}, err
	}

	if authEnabled {
		return Config{}, errors.New("AUTH_ENABLED=true is not implemented yet")
	}

	return Config{
		HTTPAddr:      stringEnv(lookup, "HTTP_ADDR", defaultHTTPAddr),
		DatabaseURL:   stringEnv(lookup, "DATABASE_URL", ""),
		AuthEnabled:   authEnabled,
		EncryptionKey: stringEnv(lookup, "ENCRYPTION_KEY", ""),
		LogLevel:      stringEnv(lookup, "LOG_LEVEL", defaultLogLevel),
	}, nil
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
