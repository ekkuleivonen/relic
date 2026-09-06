-- Preserve the original migrations so existing databases upgrade as well.
ALTER TABLE buckets RENAME COLUMN relic_config TO pithosys_config;
ALTER INDEX buckets_relic_config_gin_idx RENAME TO buckets_pithosys_config_gin_idx;

-- IF NOT EXISTS also supports databases initialized from the local trace prototype.
ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS trace_id text;
WITH RECURSIVE traces AS (
    SELECT job.id, COALESCE(job.trace_id, job.id) AS trace_id
    FROM job_runs job
    WHERE job.trace_id IS NOT NULL OR NOT EXISTS (
        SELECT 1 FROM job_runs parent
        WHERE job.requested_by_type = 'job' AND parent.id = job.requested_by_id
    )
    UNION ALL
    SELECT child.id, parent.trace_id
    FROM job_runs child JOIN traces parent ON child.requested_by_id = parent.id
    WHERE child.requested_by_type = 'job' AND child.trace_id IS NULL
)
UPDATE job_runs SET trace_id = traces.trace_id FROM traces
    WHERE job_runs.id = traces.id AND job_runs.trace_id IS NULL;
-- Orphaned cycles have no root; retain those rows with independent traces.
UPDATE job_runs SET trace_id = id WHERE trace_id IS NULL;
ALTER TABLE job_runs ALTER COLUMN trace_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS job_runs_trace_id_idx ON job_runs (trace_id);
CREATE INDEX IF NOT EXISTS job_runs_trace_active_idx ON job_runs (trace_id)
    WHERE state IN ('pending', 'running');

UPDATE collections SET query_version = 'pithosysql.v1'
    WHERE query_version = 'relicql.v1';
UPDATE collections SET query_ast = jsonb_set(query_ast, '{version}', '"pithosysql.v1"')
    WHERE query_ast->>'version' = 'relicql.v1';
