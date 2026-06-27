CREATE TABLE upstream_capture_fields (
    id text PRIMARY KEY,
    attribute_path text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    category text NOT NULL,
    origin text NOT NULL,
    capture_source text NOT NULL,
    extractor_type text NOT NULL,
    extractor_ref text NOT NULL,
    value_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT upstream_capture_fields_attribute_path_not_empty CHECK (length(trim(attribute_path)) > 0),
    CONSTRAINT upstream_capture_fields_attribute_path_prefix CHECK (attribute_path ~ '^upstream\.'),
    CONSTRAINT upstream_capture_fields_extractor_ref_not_empty CHECK (length(trim(extractor_ref)) > 0),
    CONSTRAINT upstream_capture_fields_category_valid CHECK (category IN ('required', 'optional')),
    CONSTRAINT upstream_capture_fields_origin_valid CHECK (origin IN ('platform', 'user')),
    CONSTRAINT upstream_capture_fields_capture_source_valid CHECK (capture_source IN ('head', 'tagging')),
    CONSTRAINT upstream_capture_fields_extractor_type_valid CHECK (
        extractor_type IN ('sdk_field', 'response_header', 'metadata_key', 'metadata_all', 'tag_key', 'tagging_all')
    ),
    CONSTRAINT upstream_capture_fields_value_type_valid CHECK (
        value_type IN ('string', 'integer', 'float', 'boolean', 'timestamp', 'json', 'unknown')
    )
);

CREATE UNIQUE INDEX upstream_capture_fields_attribute_path_idx ON upstream_capture_fields (attribute_path);
CREATE UNIQUE INDEX upstream_capture_fields_extractor_idx ON upstream_capture_fields (capture_source, extractor_type, extractor_ref);
CREATE INDEX upstream_capture_fields_enabled_idx ON upstream_capture_fields (enabled);
