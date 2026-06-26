CREATE TABLE relations (
    id text PRIMARY KEY,
    source_object_id text NOT NULL REFERENCES objects (id) ON DELETE CASCADE,
    target_object_id text NOT NULL REFERENCES objects (id) ON DELETE CASCADE,
    relation_type text NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by_type text,
    created_by_id text,
    created_by_name text,
    created_by_run_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT relations_source_not_target CHECK (source_object_id <> target_object_id),
    CONSTRAINT relations_type_not_empty CHECK (length(trim(relation_type)) > 0),
    CONSTRAINT relations_attributes_is_object CHECK (jsonb_typeof(attributes) = 'object')
);

CREATE INDEX relations_source_object_idx ON relations (source_object_id);
CREATE INDEX relations_target_object_idx ON relations (target_object_id);
CREATE INDEX relations_type_idx ON relations (relation_type);
CREATE INDEX relations_source_type_idx ON relations (source_object_id, relation_type);
CREATE INDEX relations_target_type_idx ON relations (target_object_id, relation_type);
