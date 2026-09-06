DROP INDEX IF EXISTS job_runs_trace_active_idx;
DROP INDEX IF EXISTS job_runs_trace_id_idx;
ALTER TABLE job_runs DROP COLUMN trace_id;
ALTER INDEX buckets_pithosys_config_gin_idx RENAME TO buckets_relic_config_gin_idx;
ALTER TABLE buckets RENAME COLUMN pithosys_config TO relic_config;
UPDATE collections SET query_version = 'relicql.v1'
    WHERE query_version = 'pithosysql.v1';
UPDATE collections SET query_ast = jsonb_set(query_ast, '{version}', '"relicql.v1"')
    WHERE query_ast->>'version' = 'pithosysql.v1';
