CREATE TABLE buckets (
    id text PRIMARY KEY,
    name text NOT NULL,
    provider text NOT NULL,
    endpoint_url text NOT NULL,
    region text NOT NULL DEFAULT '',
    bucket_name text NOT NULL,
    prefix text NOT NULL DEFAULT '',
    provider_config jsonb NOT NULL DEFAULT '{}'::jsonb,
    credential_key_id text NOT NULL,
    credential_algorithm text NOT NULL,
    credential_nonce bytea NOT NULL,
    credential_ciphertext bytea NOT NULL,
    plugin_settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT buckets_name_not_empty CHECK (length(trim(name)) > 0),
    CONSTRAINT buckets_provider_not_empty CHECK (length(trim(provider)) > 0),
    CONSTRAINT buckets_bucket_name_not_empty CHECK (length(trim(bucket_name)) > 0),
    CONSTRAINT buckets_credential_nonce_not_empty CHECK (length(credential_nonce) > 0),
    CONSTRAINT buckets_credential_ciphertext_not_empty CHECK (length(credential_ciphertext) > 0)
);

CREATE UNIQUE INDEX buckets_name_idx ON buckets (name);
CREATE INDEX buckets_provider_idx ON buckets (provider);
CREATE INDEX buckets_provider_config_gin_idx ON buckets USING gin (provider_config);
CREATE INDEX buckets_plugin_settings_gin_idx ON buckets USING gin (plugin_settings);
