# Pithosys

Pithosys catalogs and searches objects in existing S3-compatible storage. It indexes metadata, tracks bucket synchronization, and organizes objects into collections without moving their bytes.

The active implementation is a Go API and worker with a React frontend:

- `apps/api`: HTTP API, authentication, and database migrations.
- `apps/worker`: bucket synchronization, scans, and background jobs.
- `apps/web`: React application and PithosysQL editor.
- `packages`: shared storage, search, authentication, and upstream integrations.
- `_old_ref_dont_touch`: archived Python/React implementation, retained for reference.

## Development

Use Go 1.25 or newer, Node.js 22.12 or newer, and PostgreSQL. Copy `.env.example` to `.env` and supply your database connection, administrator credentials, and encryption/session keys. Preserve existing encryption keys when connecting an existing database. For local PostgreSQL without TLS, append `?sslmode=disable` to the database URL.

Run the API from the repository root; it applies database migrations on startup:

```sh
go run ./apps/api
```

Run the worker in another terminal:

```sh
go run ./apps/worker
```

Start the frontend:

```sh
cd apps/web
npm ci
npm run dev
```

The web development server proxies `/api` to `http://localhost:8080` by default. Bucket event ingestion uses the JetStream connection configured for that bucket.

## Checks

```sh
go test ./apps/api/... ./apps/worker/... ./packages/...
cd apps/web
npm run build
npm run lint
```

Database tests require `TEST_DATABASE_URL` pointing to a dedicated test database. Without it, database tests skip. Do not point it at the application database.

See [migration notes](docs/migration-2026-09-06.md) for the recovered work, database upgrade behavior, and known inherited test failures. Product direction is described in [the manifest](manifest.md).
