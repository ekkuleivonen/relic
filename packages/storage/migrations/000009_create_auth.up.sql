CREATE TABLE users (
    id text PRIMARY KEY,
    email text NOT NULL,
    display_name text,
    role text NOT NULL DEFAULT 'user',
    password_hash jsonb,
    oidc_subject text,
    disabled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_not_empty CHECK (length(trim(email)) > 0),
    CONSTRAINT users_role_valid CHECK (role IN ('admin', 'user'))
);

CREATE UNIQUE INDEX users_email_idx ON users (lower(email));
CREATE UNIQUE INDEX users_oidc_subject_idx ON users (oidc_subject) WHERE oidc_subject IS NOT NULL;

CREATE TABLE sessions (
    id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sessions_token_hash_not_empty CHECK (length(token_hash) > 0)
);

CREATE INDEX sessions_user_id_idx ON sessions (user_id);
CREATE INDEX sessions_expires_at_idx ON sessions (expires_at);
CREATE INDEX sessions_token_hash_idx ON sessions (token_hash);
