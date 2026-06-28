CREATE TABLE settings (
    key        text PRIMARY KEY,
    value      text NOT NULL,
    encrypted  boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text,
    CONSTRAINT settings_key_not_empty CHECK (length(trim(key)) > 0),
    CONSTRAINT settings_value_not_empty CHECK (length(trim(value)) > 0)
);
