CREATE TABLE collections (
    id text PRIMARY KEY,
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    query_text text NOT NULL,
    query_ast jsonb NOT NULL,
    query_version text NOT NULL,
    dependencies jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'valid',
    owner_user_id text REFERENCES users (id) ON DELETE SET NULL,
    created_by_type text,
    created_by_id text,
    created_by_name text,
    created_by_run_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT collections_name_not_empty CHECK (length(trim(name)) > 0),
    CONSTRAINT collections_query_text_not_empty CHECK (length(trim(query_text)) > 0),
    CONSTRAINT collections_status_valid CHECK (status IN ('valid', 'invalid'))
);

CREATE INDEX collections_name_idx ON collections (name);
CREATE INDEX collections_owner_user_id_idx ON collections (owner_user_id);
