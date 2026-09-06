CREATE TABLE job_runs (
    id text PRIMARY KEY,
    trace_id text NOT NULL,
    type text NOT NULL,
    state text NOT NULL DEFAULT 'pending',
    requested_by_type text,
    requested_by_id text,
    target_type text,
    target_id text,
    input jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb NOT NULL DEFAULT '{}'::jsonb,
    progress jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempt integer NOT NULL DEFAULT 1,
    max_attempts integer NOT NULL DEFAULT 1,
    available_at timestamptz NOT NULL DEFAULT now(),
    locked_by text,
    locked_at timestamptz,
    started_at timestamptz,
    finished_at timestamptz,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT job_runs_type_not_empty CHECK (length(trim(type)) > 0),
    CONSTRAINT job_runs_state_valid CHECK (state IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT job_runs_input_is_object CHECK (jsonb_typeof(input) = 'object'),
    CONSTRAINT job_runs_result_is_object CHECK (jsonb_typeof(result) = 'object'),
    CONSTRAINT job_runs_progress_is_object CHECK (jsonb_typeof(progress) = 'object'),
    CONSTRAINT job_runs_attempt_positive CHECK (attempt > 0),
    CONSTRAINT job_runs_max_attempts_positive CHECK (max_attempts > 0),
    CONSTRAINT job_runs_attempt_not_over_max CHECK (attempt <= max_attempts)
);

CREATE INDEX job_runs_type_idx ON job_runs (type);
CREATE INDEX job_runs_state_idx ON job_runs (state);
CREATE INDEX job_runs_target_idx ON job_runs (target_type, target_id);
CREATE INDEX job_runs_created_at_idx ON job_runs (created_at DESC);
CREATE INDEX job_runs_target_created_at_idx ON job_runs (target_type, target_id, created_at DESC);
CREATE INDEX job_runs_pending_claim_idx ON job_runs (available_at, created_at) WHERE state = 'pending';
CREATE INDEX job_runs_trace_id_idx ON job_runs (trace_id);
CREATE INDEX job_runs_trace_active_idx ON job_runs (trace_id) WHERE state IN ('pending', 'running');
