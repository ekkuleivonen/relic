package storage

import (
	"context"
	"fmt"
	"path/filepath"
	"testing"
	"time"

	"github.com/elei-io/pithosys/packages/testdb"
	"github.com/golang-migrate/migrate/v4"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestPithosysMigrationPreservesExistingData(t *testing.T) {
	for _, prototype := range []bool{false, true} {
		t.Run(fmt.Sprintf("prototype_trace_column_%t", prototype), func(t *testing.T) {
			ctx := context.Background()
			schema := fmt.Sprintf("pithosys_upgrade_%d", time.Now().UnixNano())
			t.Setenv(testdb.SchemaEnv, schema)
			databaseURL := testdb.URL(t, ctx)
			pool, err := pgxpool.New(ctx, databaseURL)
			if err != nil {
				t.Fatal(err)
			}
			defer pool.Close()
			defer func() { _, _ = pool.Exec(ctx, "DROP SCHEMA "+schema+" CASCADE") }()
			dir, err := filepath.Abs("migrations")
			if err != nil {
				t.Fatal(err)
			}
			m, err := migrate.New("file://"+dir, databaseURL)
			if err != nil {
				t.Fatal(err)
			}
			defer m.Close()
			if err := m.Migrate(12); err != nil {
				t.Fatal(err)
			}
			if _, err := pool.Exec(ctx, `
    INSERT INTO buckets (id, name, upstream, endpoint_url, bucket_name,
      credential_key_id, credential_algorithm, credential_nonce, credential_ciphertext, relic_config)
    VALUES ('existing', 'existing', 's3', 'https://example.com', 'data', 'key', 'aes', '\x01', '\x02', '{"scan":{"enabled":false,"interval":"12h"}}');
    INSERT INTO job_runs (id, type) VALUES ('existing-job', 'sync_bucket');
    INSERT INTO job_runs (id, type, requested_by_type, requested_by_id) VALUES ('child-job', 'import_objects', 'job', 'existing-job');
    INSERT INTO collections (id, name, query_text, query_ast, query_version)
    VALUES ('existing-collection', 'existing', 'SELECT * FROM objects', '{"version":"relicql.v1","from":"objects"}', 'relicql.v1');
   `); err != nil {
				t.Fatal(err)
			}
			if prototype {
				if _, err := pool.Exec(ctx, `ALTER TABLE job_runs ADD COLUMN trace_id text NOT NULL DEFAULT 'original-trace';
     CREATE INDEX job_runs_trace_id_idx ON job_runs (trace_id);
     CREATE INDEX job_runs_trace_active_idx ON job_runs (trace_id) WHERE state IN ('pending','running');`); err != nil {
					t.Fatal(err)
				}
			}
			if err := m.Up(); err != nil {
				t.Fatal(err)
			}
			var trace, interval, version, astVersion string
			if err := pool.QueryRow(ctx, `SELECT trace_id FROM job_runs WHERE id='existing-job'`).Scan(&trace); err != nil {
				t.Fatal(err)
			}
			wantTrace := "existing-job"
			if prototype {
				wantTrace = "original-trace"
			}
			var childTrace string
			if err := pool.QueryRow(ctx, `SELECT trace_id FROM job_runs WHERE id='child-job'`).Scan(&childTrace); err != nil {
				t.Fatal(err)
			}
			if childTrace != wantTrace {
				t.Fatalf("child trace = %q, want %q", childTrace, wantTrace)
			}
			if trace != wantTrace {
				t.Fatalf("trace = %q, want %q", trace, wantTrace)
			}
			if err := pool.QueryRow(ctx, `SELECT pithosys_config->'scan'->>'interval' FROM buckets WHERE id='existing'`).Scan(&interval); err != nil {
				t.Fatal(err)
			}
			if interval != "12h" {
				t.Fatalf("bucket config lost: %q", interval)
			}
			if err := pool.QueryRow(ctx, `SELECT query_version, query_ast->>'version' FROM collections WHERE id='existing-collection'`).Scan(&version, &astVersion); err != nil {
				t.Fatal(err)
			}
			if version != "pithosysql.v1" || astVersion != version {
				t.Fatalf("query versions = %q / %q", version, astVersion)
			}
			if err := m.Steps(-1); err != nil {
				t.Fatal(err)
			}
			if err := pool.QueryRow(ctx, `SELECT relic_config->'scan'->>'interval' FROM buckets WHERE id='existing'`).Scan(&interval); err != nil {
				t.Fatal(err)
			}
			if interval != "12h" {
				t.Fatal("rollback lost bucket config")
			}
		})
	}
}
