# Pithosys

[![CI](https://github.com/elei-io/pithosys/actions/workflows/ci.yml/badge.svg)](https://github.com/elei-io/pithosys/actions/workflows/ci.yml)

**Find and organize objects across S3-compatible storage without moving their bytes.**

Pithosys is a metadata catalog built with Go, PostgreSQL, and React. It reconciles bucket listings, captures metadata and its provenance, and lets you search using PithosysQL and save queries as collections.

![Object search with synthetic demo data](docs/images/objects.png)

## Try the local demo

Requires Docker with Compose, a shell, and OpenSSL. From a checkout:

```sh
./scripts/demo.sh up
```

Open **http://localhost:8088**. Sign in as `admin@example.com` using `SUPERUSER_PASSWORD` from the generated `.demo/env` file. The command builds the API, worker, and frontend, starts private PostgreSQL and S3 containers, seeds 128 synthetic objects, and verifies indexing, search, annotation, and collection creation. First startup downloads images and builds dependencies.

Only the web port is bound, on localhost. Demo data and generated secrets are separate from `.env` and existing services. To stop, use `./scripts/demo.sh down`; Docker volumes and credentials are retained. To rerun the smoke check, use `./scripts/demo.sh check`. The demo is intended for local evaluation, not public hosting.

## What works today

- S3-compatible bucket catalogs with paginated synchronization and metadata capture.
- Durable background jobs, listing checkpoints, parent/child traces, and progress reporting.
- PithosysQL search, user annotations, and saved-query collections.
- Password authentication, administrator controls, and optional OIDC.
- Optional JetStream event ingestion, verification scans, and duplicate relations.

**Status: alpha.** The local demo covers the primary catalog workflow. OIDC, notification integration, large catalogs, and multi-worker failure recovery need deployment-specific validation. The repository's license/ownership review and historical credential remediation remain open; this is not yet a completed open-source release. See the [release checklist](docs/public-release-checklist.md) and [security boundary](SECURITY.md).

## A query example

```sql
FROM objects
WHERE attr('user.reviewed') = true
LIMIT 100
```

Queries bind known attribute paths and compile to parameterized PostgreSQL queries. Search results are capped at 1,000 objects per request. The [architecture notes](docs/architecture/overview.md) explain the design, crash-recovery tradeoffs, and limitations. [Demo measurements](docs/demo-measurements.md) report a small local run, not a scalability claim.

## Develop

Use Go 1.26.7+, Node.js 24, and PostgreSQL 17. Copy `.env.example` to `.env`, supply a database connection and administrator password, and generate distinct session/encryption keys with `openssl rand -base64 32`. Preserve encryption keys for existing databases. Do not reuse demo credentials for real deployments.

```sh
go run ./apps/api     # Applies migrations on startup.
go run ./apps/worker  # In another terminal.
```

```sh
cd apps/web
npm ci
npm run dev
```

The web development server proxies `/api` to localhost:8080. API documentation is available at `/api/docs`.

## Validate

Use a dedicated test database and leave `TEST_DATABASE_SCHEMA` unset; tests create and remove isolated schemas. Database tests skip if `TEST_DATABASE_URL` is absent.

```sh
export TEST_DATABASE_URL='postgres://pithosys:pithosys@localhost:5432/pithosys_test?sslmode=disable'
go test -race -p 4 -timeout 180s ./...
go vet ./...
go run golang.org/x/vuln/cmd/govulncheck@v1.7.0 ./...
cd apps/web
npm ci
npm run lint
npm run build
npm audit --audit-level=moderate
npx playwright install chromium
npm run test:e2e # Requires the running, seeded Docker demo.
```

[Contributing](CONTRIBUTING.md) · [Design decisions](docs/decisions) · [Product vision](docs/design/product-vision.md) · [Migration history](docs/migration-2026-09-06.md)

The earlier Python implementation is archived in Git history at `archive/python-reference`.
