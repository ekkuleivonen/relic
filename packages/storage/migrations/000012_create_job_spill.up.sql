CREATE TABLE job_spill (
    job_run_id text NOT NULL REFERENCES job_runs(id) ON DELETE CASCADE,
    spill_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT job_spill_key_not_empty CHECK (length(trim(spill_key)) > 0),
    PRIMARY KEY (job_run_id, spill_key)
);

CREATE INDEX job_spill_job_run_id_idx ON job_spill (job_run_id);
