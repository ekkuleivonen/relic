# ADR 0005: UI Authentication

## Status

Accepted

## Context

Relic needs human authentication for the admin UI before machine-facing API tokens are introduced. The product requires:

- Closed registration: only provisioned users may sign in
- Dual login methods per user: password and OIDC SSO
- Bootstrap admin reconciliation from environment variables
- Server-side sessions for the web UI
- A clear extension point for Bearer API tokens later

## Decision

Implement Phase 1 UI auth with the following model.

### Users

- One row per email in `users`
- `role`: `admin` or `user`
- Optional `password_hash` (Argon2id envelope in JSONB)
- Optional `oidc_subject` (linked on first successful OIDC login)
- Either credential may be absent until configured; both may coexist

### Registration

Admins create users through the UI. Login endpoints reject unknown emails. There is no self-signup.

### Bootstrap admin

On startup, Relic reconciles `SUPERUSER_EMAIL`:

- If no user exists: create admin with optional password hash from `SUPERUSER_PASSWORD`
- If user exists: ensure `role=admin`; update password hash when env password is provided
- Same row whether the person later links OIDC or was pre-created by another admin

### Sessions

- Opaque random cookie value (`relic_session`)
- SHA-256 hash stored in `sessions`
- HttpOnly, SameSite=Lax, Secure outside local dev
- Validated by HTTP middleware before protected routes

### OIDC

- Optional configuration (`OIDC_*` env vars are all-or-nothing)
- Authorization code flow via `coreos/go-oidc` and `golang.org/x/oauth2`
- State parameter signed with `SESSION_SECRET_BASE64`
- Callback matches existing user by email and links `oidc_subject`

### Authorization

- Middleware protects all `/api/*` routes except health, auth login/logout/config, and OIDC endpoints
- Admin-only routes (`/api/users`) check `role=admin` in handlers
- Job provenance uses `requested_by_type=user` and `requested_by_id=<user id>` when auth is enabled

### Frontend

- React Query hooks for session, auth config, and user management
- Login page supports password and conditional SSO button

## Consequences

- Auth is required at startup; missing bootstrap or session configuration fails clearly
- Phase 2 API tokens can extend the same middleware with a Bearer branch without changing the session/OIDC model

## Deferred

- API token table, generation UI, and Bearer middleware (Phase 2)
