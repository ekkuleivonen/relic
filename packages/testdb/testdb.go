package testdb

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"regexp"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	DatabaseURLEnv = "TEST_DATABASE_URL"
	SchemaEnv      = "TEST_DATABASE_SCHEMA"
	DefaultSchema  = "relic_test"
)

var (
	schemaNamePattern = regexp.MustCompile(`^[a-zA-Z_][a-zA-Z0-9_]*$`)
	createdSchemas    sync.Map
)

func URL(t testing.TB, ctx context.Context) string {
	t.Helper()

	databaseURL := os.Getenv(DatabaseURLEnv)
	if databaseURL == "" {
		t.Skipf("%s is not set", DatabaseURLEnv)
	}

	schema := os.Getenv(SchemaEnv)
	if schema == "" {
		schema = DefaultSchema
	}
	if !schemaNamePattern.MatchString(schema) {
		t.Fatalf("%s = %q is not a valid Postgres schema name", SchemaEnv, schema)
	}

	ensureSchema(t, ctx, databaseURL, schema)
	return withTestOptions(t, databaseURL, schema)
}

func ensureSchema(t testing.TB, ctx context.Context, databaseURL string, schema string) {
	t.Helper()

	key := databaseURL + "\x00" + schema
	if _, loaded := createdSchemas.LoadOrStore(key, true); loaded {
		return
	}

	pool, err := connect(ctx, withTimeoutOptions(t, databaseURL))
	if err != nil {
		createdSchemas.Delete(key)
		t.Fatalf("connect to test database: %v", err)
	}
	defer pool.Close()

	if _, err := pool.Exec(ctx, "CREATE SCHEMA IF NOT EXISTS "+quoteIdentifier(schema)); err != nil {
		createdSchemas.Delete(key)
		t.Fatalf("create test schema %q: %v", schema, err)
	}
}

func connect(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse database URL: %w", err)
	}

	connectCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	pool, err := pgxpool.NewWithConfig(connectCtx, cfg)
	if err != nil {
		return nil, fmt.Errorf("create database pool: %w", err)
	}
	if err := pool.Ping(connectCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping database: %w", err)
	}

	return pool, nil
}

func withTestOptions(t testing.TB, databaseURL string, schema string) string {
	t.Helper()

	parsed, err := url.Parse(databaseURL)
	if err != nil {
		t.Fatalf("parse %s: %v", DatabaseURLEnv, err)
	}

	query := parsed.Query()
	query.Set("options", postgresOptions(
		"search_path="+schema+",public",
		"statement_timeout=15s",
		"lock_timeout=5s",
	))
	parsed.RawQuery = query.Encode()

	return parsed.String()
}

func withTimeoutOptions(t testing.TB, databaseURL string) string {
	t.Helper()

	parsed, err := url.Parse(databaseURL)
	if err != nil {
		t.Fatalf("parse %s: %v", DatabaseURLEnv, err)
	}

	query := parsed.Query()
	query.Set("options", postgresOptions(
		"statement_timeout=15s",
		"lock_timeout=5s",
	))
	parsed.RawQuery = query.Encode()

	return parsed.String()
}

func quoteIdentifier(identifier string) string {
	return `"` + strings.ReplaceAll(identifier, `"`, `""`) + `"`
}

func postgresOptions(settings ...string) string {
	options := make([]string, 0, len(settings))
	for _, setting := range settings {
		options = append(options, "-c "+setting)
	}

	return strings.Join(options, " ")
}

func MigrationTimeoutError(err error) error {
	if err == nil {
		return nil
	}

	return fmt.Errorf("test database migration failed; check for stale migration advisory locks or long-running schema changes: %w", err)
}
