# Events reference

Relic maintains two **implemented** event logs plus a **planned** folder subscription surface.

| Log | Table | API | Audience |
|-----|-------|-----|----------|
| **Audit** | `audit_events` | `GET /api/audit-events` (admin) | Security, compliance, ops |
| **Subscription (files)** | `file_events` | `GET /api/file-events` (ACL-filtered) | Integrators polling filesystem changes |
| **Subscription (folders)** | — *planned* | — | Same poll model as files; not implemented yet |

**Retention:** audit and file events are trimmed after `EVENT_RETENTION_DAYS` (default 90). Probe samples use `PROBES_RETENTION_DAYS` (default 14) in a separate table.

---

## Envelope fields

### Audit event row

Stored in `audit_events`. API field `metadata` maps to DB column `meta`.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `operation` | string | Dot-separated kind (see below) |
| `status` | `succeeded` \| `failed` \| `skipped` | |
| `actor_id` | UUID \| null | User who caused the action, when known |
| `request_id` | string \| null | HTTP request correlation |
| `job` | string \| null | Background worker name |
| `batch_id` | UUID \| null | Correlates events from one maintenance run |
| `storage_backend_id` | UUID \| null | |
| `blob_id` | UUID \| null | Not FK — may reference purged blobs |
| `duration_ms` | int \| null | |
| `metadata` | object | Operation-specific payload |
| `created_at` / `updated_at` | datetime | |

**Emission paths**

- `uow.audit.record(...)` — user-initiated actions. **No-op when `event_context` is missing** (see `infra/db/repositories/audit.py`).
- `uow.audit.emit(...)` — jobs and cases that supply fields directly (e.g. failed login).

### File event row

Stored in `file_events`. Monotonic `seq` is the poll cursor.

| Field | Type | Notes |
|-------|------|-------|
| `seq` | int | Strictly increasing; allocate via `max(seq)+1` |
| `id` | UUID | |
| `event_type` | string | One of `file.*` (see below) |
| `created_at` | datetime | |
| `file_id` | UUID | |
| `folder_id` | UUID | ACL anchor and filter key |
| `actor_id` | UUID \| null | Defaults to file owner when omitted at emit time |
| `request_id` | string \| null | Rarely set today |
| `payload` | object | Event-specific body |

**Poll:** `GET /api/file-events?after=<seq>&folder_id=&recursive=&types=&limit=`

Non-admin users only receive events for folders they can **READ**. Admins see all.

**ACL anchor:** for `file.moved`, `folder_id` is the **destination** folder. Subscribers on the source folder do not see move-out events (same as destination-centric design today).

---

## Audit events

### Auth

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `auth.login.succeeded` | succeeded | `POST /api/auth/login` → `application/control_plane/auth_mutations.login` | `{ "email": string }` |
| `auth.login.failed` | failed | Same, on bad credentials | `{ "email": string }` |
| `auth.logout` | succeeded | `POST /api/auth/logout` → `auth_mutations.logout` | `{ "email": string }` if user known, else `{}` |

Bearer access-key API auth does **not** emit audit events.

---

### Users

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `user.created` | succeeded | `POST /api/users` → `user_mutations.create_user` | `{ "user_id", "email", "role" }` |
| `user.updated` | succeeded | `PATCH /api/users/{id}` → `user_mutations.update_user` | `{ "user_id", "email", "changed_fields": string[] }` |
| `user.deleted` | succeeded | `DELETE /api/users/{id}` → `user_mutations.delete_user` | `{ "user_id", "email" }` |

Requires `event_context` from request headers.

---

### Access keys

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `access_key.created` | succeeded | `POST /api/access-keys` → `access_key_mutations.create_access_key` | `{ "access_key_id", "key_id", "actor_id", "name" }` |
| `access_key.revoked` | succeeded | `POST /api/access-keys/{key_id}/revoke` → `access_key_mutations.revoke_access_key` | `{ "access_key_id", "key_id", "actor_id" }` — only when newly revoked |
| `access_key.deleted` | succeeded | `DELETE /api/access-keys/{key_id}` → `access_key_mutations.delete_access_key` | `{ "access_key_id", "key_id", "actor_id" }` |

---

### Folder access (ACL)

Emits via `create_audit_event` in `infra/db/stores/folder_access.py` (not the UoW port). Same `event_context` guard.

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `folder.access.granted` | succeeded | `POST /api/folder-access` → `grant_folder_access` (new row) | `{ "access_id", "actor_id", "folder_id", "permissions", "folder_path" }` |
| `folder.access.updated` | succeeded | Same (existing row updated) | Same shape |
| `folder.access.revoked` | succeeded | `DELETE /api/folder-access/{id}` → `revoke_folder_access` | `{ "access_id", "actor_id", "folder_id", "permissions" }` |

`permissions` is an integer bitfield (`READ=1`, `WRITE=2`, `DELETE=4`, `ENRICH=8`).

Folder CRUD (create/rename/move/delete/duplicate) does **not** audit today.

---

### Storage backends (control plane)

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `storage_backend.created` | succeeded | `POST /api/storage-backends` → `storage_backend_mutations.create_storage_backend` | `{ "storage_backend_id", "name", "duration_ms", "db_latency_ms" }` |
| `storage_backend.updated` | succeeded | `PATCH /api/storage-backends/{id}` → `update_storage_backend` | `{ "storage_backend_id", "name", "changed_fields", "duration_ms", "db_latency_ms" }` |
| `storage_backend.deleted` | succeeded | `DELETE /api/storage-backends/{id}` → `delete_storage_backend` | `{ "storage_backend_id", "name", "duration_ms", "db_latency_ms" }` |
| `storage_backend.drain_started` | succeeded | `drain_storage_backend` when blobs remain | `{ "storage_backend_id", "blob_count" }` |
| `storage_backend.drained` | succeeded | After successful drain | `{ "storage_backend_id", "moved", "skipped", "failed", "scanned" }` |

**Note:** `POST /api/storage-backends/{id}/drain` does not pass `event_context` today, so `drain_started` / `drained` are **not emitted** from the HTTP route until that is wired.

Manual `POST /api/storage-backends/{id}/probe` writes to `storage_backend_probes` only — no audit row.

---

### Blob purge

**Job:** `purge_dereferenced_blobs`  
**Worker:** `purge_dereferenced_blobs_worker`  
**Code:** `infra/maintenance/storage.py` → `purge_dereferenced_blobs_batch`

| Operation | Status | When | Metadata |
|-----------|--------|------|----------|
| `blob.purged` | succeeded | Remote + DB row deleted | `{ "freed_bytes", "bucket_key" }` |
| `blob.purge_failed` | failed | Exception during purge | `{ "bucket_key", "size_bytes", "error_class", "error_message" }` |

Row fields: `batch_id`, `storage_backend_id`, `blob_id`, `duration_ms`.

---

### Storage backend probe (batch)

**Job:** `storage_backend_probe`  
**Worker:** `refresh_all_storage_backend_probes_worker`  
**Code:** `probe_all_storage_backends`

| Operation | Status | When | Metadata |
|-----------|--------|------|----------|
| `bucket.probe_failed` | failed | Probe unreachable or exception | On unreachable: `{ "put_ms", "head_ms", "get_ms", "delete_ms" }`. On exception: `{ "error_class", "error_message" }` |

Successful probes are **not** audited (stored in `storage_backend_probes`).

**Legacy name:** operation still uses `bucket.probe_failed`; domain entity is `storage_backend`.

---

### Probe retention trim

**Job:** `trim_storage_backend_probes`  
**Worker:** `trim_old_storage_backend_probes_worker`

| Operation | Status | When | Metadata |
|-----------|--------|------|----------|
| `storage_backend_probe.trimmed` | succeeded | `deleted_rows > 0` | `{ "retention_days", "deleted_rows" }` |

---

### Blob migration (demote / drain / promote)

Per-blob events via `_record_migration_event` in `infra/maintenance/storage.py`.

Shared metadata base:

```json
{
  "from_storage_backend_id": "uuid",
  "to_storage_backend_id": "uuid",
  "size_bytes": 0,
  "db_latency_ms": 0,
  "remote_latency_ms": 0,
  "reason": "string"
}
```

On failure, adds `error_class`, `error_message`.  
`storage_backend_id` on the row = destination if migrated, else source.

**Skip/migration `reason` values** (from `BlobMigrationResult`):  
`same_bucket`, `source_bucket_missing`, `destination_full`, `destination_headroom_exceeded`, `remote_copy_failed`, `db_commit_failed`.

#### Demote pressured backends

**Job:** `demote_pressured_buckets`  
**Worker:** `demote_pressured_buckets_worker`

| Operation | Status |
|-----------|--------|
| `blob.demoted` | succeeded |
| `blob.demotion_failed` | failed |
| `blob.demotion_skipped` | skipped |

Extra explicit skip (no destination with headroom):

| Operation | Status | Metadata |
|-----------|--------|----------|
| `blob.demotion_skipped` | skipped | `{ "from_storage_backend_id", "reason": "no_colder_bucket_with_headroom", "size_bytes" }` |

#### Drain storage backend (maintenance batch)

**Job:** `drain_storage_backend`  
**Code:** `drain_storage_backend_batch` (also used by admin drain use case)

| Operation | Status |
|-----------|--------|
| `blob.drained` | succeeded |
| `blob.drain_failed` | failed |
| `blob.drain_skipped` | skipped |

Explicit skip when no colder destination: same pattern as demotion with `"reason": "no_colder_bucket_with_headroom"`.

#### Promote recently accessed

**Job:** `promote_recently_accessed`  
**Worker:** `promote_recently_accessed_worker`

| Operation | Status |
|-----------|--------|
| `blob.promoted` | succeeded |
| `blob.promotion_failed` | failed |
| `blob.promotion_skipped` | skipped |

When no hotter destination exists, the loop **continues silently** — no skip audit event.

---

### Event retention & multipart cleanup

**Workers:** `trim_old_audit_events_worker`, `abort_incomplete_multipart_uploads_worker`

| Operation | Job | Status | Metadata |
|-----------|-----|--------|----------|
| `audit_event.trimmed` | `trim_audit_events` | succeeded | `{ "retention_days", "deleted_rows" }` |
| `file_event.trimmed` | `trim_file_events` | succeeded | `{ "retention_days", "deleted_rows" }` |
| `multipart_upload.aborted` | `abort_incomplete_multipart_uploads` | succeeded | `{ "abort_after_hours", "deleted_rows" }` |

Only emitted when `deleted_rows > 0`.

---

## File events (subscription log)

Defined in `domain/file_events/types.py`. Emitted from `application/control_plane/file_event_emission.py` in the **same transaction** as the mutation.

### `file.created`

| | |
|--|--|
| **Trigger sites** | |
| S3 PUT (new object) | `application/gateway/object_mutations.put_object` → `emit_put_object_events` (`origin: "upload"`) |
| S3 multipart complete (new) | `complete_multipart_upload` → `emit_multipart_complete_events` (`origin: "multipart"`) |
| S3 CopyObject | `copy_object` (`origin: "copy"`, includes `source_file_id`) |
| Folder duplicate | `duplicate_folder` → `clone_files` (`origin: "duplicate"`, includes `source_file_id`) |

**Payload**

```json
{
  "name": "string",
  "blob_id": "uuid",
  "size_bytes": 0,
  "mimetype": "string | null",
  "extension": "string | null",
  "meta": {},
  "origin": "upload | multipart | copy | duplicate",
  "source_file_id": "uuid"
}
```

`source_file_id` only for `copy` and `duplicate`.

---

### `file.content_updated`

| | |
|--|--|
| **Trigger sites** | |
| S3 PUT (overwrite) | `emit_put_object_events` when `previous_blob_id != blob.id` |
| S3 multipart complete (overwrite) | Same via `emit_multipart_complete_events` |

**Payload**

```json
{
  "name": "string",
  "blob_id": "uuid",
  "size_bytes": 0,
  "mimetype": "string | null",
  "extension": "string | null",
  "previous_blob_id": "uuid",
  "meta": {}
}
```

---

### `file.meta_updated`

| | |
|--|--|
| **Trigger sites** | |
| JSON API | `PATCH /api/files/{id}` → `patch_file_meta` |
| Bulk | `POST /api/files/bulk-patch-meta` → `bulk_patch_file_meta` (one event per file) |

**Payload**

```json
{
  "name": "string",
  "blob_id": "uuid",
  "meta": {}
}
```

---

### `file.renamed`

| | |
|--|--|
| **Trigger sites** | |
| JSON API | `PATCH /api/files/{id}/rename` → `rename_file` |
| Move within same folder | `move_file` when `from_folder_id == destination.id` and name changes |

**Payload**

```json
{
  "name": "string",
  "previous_name": "string",
  "blob_id": "uuid"
}
```

---

### `file.moved`

| | |
|--|--|
| **Trigger sites** | |
| JSON API | `PATCH /api/files/{id}/move` → `move_file` (cross-folder) |
| Bulk | `POST /api/files/bulk-move` → `bulk_move_files` (one event per file) |

**Payload**

```json
{
  "name": "string",
  "previous_name": "string",
  "from_folder_id": "uuid",
  "to_folder_id": "uuid",
  "blob_id": "uuid"
}
```

`folder_id` on the event row = `to_folder_id`.

---

### `file.deleted`

| | |
|--|--|
| **Trigger sites** | |
| JSON API | `DELETE /api/files/{id}` → `delete_file` → `remove_file_record` |
| Bulk | `POST /api/files/bulk-delete` |
| S3 DeleteObject | `application/gateway/delete_object` → `remove_file_record` |
| Recursive folder delete | `delete_folder` (one event per file before row delete) |

**Payload**

```json
{
  "name": "string",
  "blob_id": "uuid"
}
```

---

## Folder events (planned)

Not implemented. Intended for the **same subscription log** as files (extend `file_events` or rename to `filesystem_events`), not a separate table.

These belong in subscription (integrators need them), **not** audit:

| Event type | Trigger site (future) | Proposed payload |
|------------|----------------------|------------------|
| `folder.created` | `POST /api/folders` → `create_folder` | `{ "name", "parent_id" }` |
| `folder.renamed` | `PATCH /api/folders/{id}` (name change) → `update_folder` | `{ "name", "previous_name", "parent_id" }` |
| `folder.moved` | `PATCH /api/folders/{id}` (parent change) → `update_folder` | `{ "name", "from_parent_id", "to_parent_id" }` |
| `folder.deleted` | `DELETE /api/folders/{id}` → `delete_folder` | `{ "name", "parent_id", "recursive", "descendant_folder_count", "file_count" }` |
| `folder.duplicated` | `POST /api/folders/{id}/duplicate` → `duplicate_folder` | `{ "name", "source_folder_id", "destination_parent_id", "recursive" }` |

**Emit nested `folder.created`** for each cloned subfolder on duplicate, or rely on a single root `folder.duplicated` plus `file.created` events (today duplicate only emits `file.created`).

**Stay audit-only (not subscription):**

- `folder.access.*`
- `preferred_storage_backend_id` changes on folders (admin policy)

**Optional audit summaries** (low volume, admin forensics): `folder.deleted`, `folder.duplicated` with counts — without duplicating per-file detail already in `file.*`.

---

## What does not emit events

| Action | Notes |
|--------|-------|
| Folder create / rename / move / empty delete | structlog only |
| Admin clear audit log | `DELETE /api/audit-events` |
| Storage backend manual probe | `storage_backend_probes` table |
| Successful batch probes | probe table + metrics |
| Blob touch / access time update | `touch_blob_access` |
| Multipart abort (user or worker) | worker abort only audits aggregate `multipart_upload.aborted` |
| Search, list, read, presign | read paths |

---

## Known inconsistencies

| Issue | Detail |
|-------|--------|
| `bucket.probe_failed` | Legacy operation name; entity is `storage_backend` |
| Admin UI filter lists | `client/src/pages/admin/audit-events-page.tsx` still lists `bucket.*` ops/jobs; server emits `storage_backend.*` |
| Drain API audit gap | `POST .../drain` omits `event_context` → no `storage_backend.drain_*` rows |
| Promote skip silence | No audit event when no hotter destination (unlike demote/drain) |
| Move-out visibility | `file.moved` / planned `folder.moved` anchored on destination — source-folder subscribers miss move-out |

---

## Source index

| Area | Primary files |
|------|----------------|
| Audit port | `server/ports/audit.py`, `server/infra/db/repositories/audit.py`, `server/infra/db/stores/audit_events.py` |
| File emit helpers | `server/application/control_plane/file_event_emission.py`, `server/application/gateway/file_event_emission.py` |
| File event types | `server/domain/file_events/types.py` |
| Maintenance audit | `server/infra/maintenance/storage.py`, `server/application/maintenance/retention.py` |
| Workers | `server/workers/maintenance.py` |
| APIs | `server/api/audit_events.py`, `server/api/file_events.py` |
