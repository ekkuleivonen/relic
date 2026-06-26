CREATE TABLE objects (
    id text PRIMARY KEY,
    bucket_id text NOT NULL REFERENCES buckets (id) ON DELETE CASCADE,
    key text NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    attribute_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT objects_bucket_id_not_empty CHECK (length(trim(bucket_id)) > 0),
    CONSTRAINT objects_key_not_empty CHECK (length(key) > 0),
    CONSTRAINT objects_attributes_is_object CHECK (jsonb_typeof(attributes) = 'object'),
    CONSTRAINT objects_attribute_provenance_is_object CHECK (jsonb_typeof(attribute_provenance) = 'object')
);

CREATE UNIQUE INDEX objects_bucket_key_idx ON objects (bucket_id, key);
CREATE INDEX objects_bucket_idx ON objects (bucket_id);
CREATE INDEX objects_bucket_key_prefix_idx ON objects (bucket_id, key text_pattern_ops);
CREATE INDEX objects_attributes_gin_idx ON objects USING gin (attributes);
