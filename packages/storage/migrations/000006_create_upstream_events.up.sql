CREATE TABLE upstream_events (
    id text PRIMARY KEY,
    bucket_id text REFERENCES buckets (id) ON DELETE SET NULL,
    upstream_bucket_name text NOT NULL,
    event_name text NOT NULL,
    object_key text NOT NULL DEFAULT '',
    envelope jsonb NOT NULL,
    dedupe_key text NOT NULL,
    transport text NOT NULL,
    state text NOT NULL DEFAULT 'pending',
    event_time timestamptz,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT upstream_events_upstream_bucket_name_not_empty CHECK (length(trim(upstream_bucket_name)) > 0),
    CONSTRAINT upstream_events_event_name_not_empty CHECK (length(trim(event_name)) > 0),
    CONSTRAINT upstream_events_dedupe_key_not_empty CHECK (length(trim(dedupe_key)) > 0),
    CONSTRAINT upstream_events_transport_not_empty CHECK (length(trim(transport)) > 0),
    CONSTRAINT upstream_events_transport_valid CHECK (transport IN ('webhook', 'jetstream')),
    CONSTRAINT upstream_events_state_valid CHECK (state IN ('pending', 'processed', 'skipped', 'failed')),
    CONSTRAINT upstream_events_envelope_is_object CHECK (jsonb_typeof(envelope) = 'object')
);

CREATE UNIQUE INDEX upstream_events_dedupe_key_idx ON upstream_events (dedupe_key);
CREATE INDEX upstream_events_bucket_id_idx ON upstream_events (bucket_id);
CREATE INDEX upstream_events_state_received_at_idx ON upstream_events (state, received_at);
CREATE INDEX upstream_events_pending_claim_idx ON upstream_events (received_at) WHERE state = 'pending';
CREATE INDEX upstream_events_upstream_bucket_name_idx ON upstream_events (upstream_bucket_name);
