CREATE TABLE attribute_catalog (
    path text PRIMARY KEY,
    value_type text NOT NULL,
    source text NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT attribute_catalog_path_not_empty CHECK (length(trim(path)) > 0),
    CONSTRAINT attribute_catalog_source_valid CHECK (
        source IN ('builtin', 'registered', 'observed')
    ),
    CONSTRAINT attribute_catalog_value_type_valid CHECK (
        value_type IN ('string', 'integer', 'float', 'boolean', 'timestamp', 'json', 'unknown')
    )
);

CREATE INDEX attribute_catalog_source_idx ON attribute_catalog (source);
