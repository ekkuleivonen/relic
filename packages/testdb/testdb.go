package testdb

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
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
	if runtimeURL := os.Getenv("DATABASE_URL"); runtimeURL != "" && runtimeURL == databaseURL {
		t.Fatalf("%s must not equal DATABASE_URL; use a separate test database because this Postgres endpoint does not reliably isolate tests by schema", DatabaseURLEnv)
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

func WithMigrationLock(t testing.TB, migrate func() error) error {
	t.Helper()

	lockPath := filepath.Join(os.TempDir(), "relic-test-migrations.lock")
	file, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return fmt.Errorf("open migration lock file: %w", err)
	}
	defer file.Close()

	if err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX); err != nil {
		return fmt.Errorf("acquire migration lock: %w", err)
	}
	defer func() {
		_ = syscall.Flock(int(file.Fd()), syscall.LOCK_UN)
	}()

	return migrate()
}

func MigrateIfNeeded(t testing.TB, ctx context.Context, databaseURL string, requiredTable string, migrate func() error) error {
	t.Helper()

	return WithMigrationLock(t, func() error {
		exists, err := HasTable(ctx, databaseURL, requiredTable)
		if err != nil {
			return err
		}
		if exists {
			return nil
		}

		return migrate()
	})
}

func HasTable(ctx context.Context, databaseURL string, table string) (bool, error) {
	pool, err := connect(ctx, databaseURL)
	if err != nil {
		return false, err
	}
	defer pool.Close()

	var name *string
	if err := pool.QueryRow(ctx, "SELECT to_regclass($1)::text", table).Scan(&name); err != nil {
		return false, fmt.Errorf("check test table %q: %w", table, err)
	}

	return name != nil && *name != "", nil
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
