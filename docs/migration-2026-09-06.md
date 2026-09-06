# Repository migration — September 6, 2026

## Source selection and recovered work

The source repository's `redo` branch (`e065b70`) is 33 commits ahead of the destination's former `main` (`7b22030`). It includes the source's local `main` fix (`b7b57a0`) and `v2` history. The rewrite moved the earlier Python storage gateway into `_old_ref_dont_touch` and introduced the Go metadata catalog. Development continued through June 28, with local edits dated July 4.

Commit `4d66461` preserves all 66 modified or new source files before renaming: 6,646 insertions and 326 deletions. A byte comparison of all 914 tracked and non-ignored new source files against that commit found no differences. The recovered work covers job traces, spill storage, resumable bucket synchronization, fanout/completion, scheduler behavior, API responses, and UI progress reporting.

The current implementation is promoted to `main`, retaining the earlier commits in history. The original source directory is preserved. Ignored dependencies, build outputs, and runtime data are not committed. The local `.env` was copied unchanged with private permissions and remains Git-ignored; its existing service addresses and credentials are preserved.

## Naming and database upgrades

The active Go module is `github.com/elei-io/pithosys`; application branding, package names, source filenames, imports, configuration examples, and reference documentation use Pithosys. The query language is PithosysQL (`pithosysql.v1`).

Migration 13 upgrades the bucket configuration column and index, backfills job traces while preserving parent/child grouping and existing prototype trace IDs, and updates saved collection query versions. Original migrations 1 and 2 remain unchanged so already-installed databases can upgrade. Old names remain intentionally in those historical migrations and migration/rollback fixtures.

API clients must use `pithosys_config` and `pithosysql.v1`. Renamed session cookies require a fresh sign-in. Default JetStream consumer names now start with `pithosys-`; explicitly configured consumer names remain unchanged. Coordinate consumers when switching a running installation to avoid unintended replay. Database names, credentials, external resources, and running services are not renamed by this repository migration.

## Validation

- Backend compilation and tests without an external database pass; database-dependent tests skip in that mode.
- Frontend TypeScript checking and production build pass.
- Upgrade and rollback tests pass against an isolated PostgreSQL 17 database, including both the original schema and the local trace prototype, preservation of bucket settings, job trace ancestry, and saved query versions.
- Incorrect migration-directory paths in five API/worker test helpers were corrected.
- The source frontend lint baseline has 11 errors and 2 warnings. One redundant assignment in recovered progress code was fixed; the remaining 10 errors and 2 warnings are inherited React lint issues.
- Full PostgreSQL integration runs on both source and destination reproduce failures in import/refresh fixtures, scan/sync expectations, runner setup, and storage fixtures. Scheduler tests stalled in both runs and were interrupted. These inherited failures mean the full integration suite is not green; they are not evidence of a clean production release.

The source's uncommitted work is preserved even where its tests expose unfinished behavior. This migration does not claim to complete that feature development.
