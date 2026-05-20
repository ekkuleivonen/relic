# Events reference

Relic has two event logs:

| Log | Table | API | Audience |
|-----|-------|-----|----------|
| **Audit** | `audit_events` | `GET /api/audit-events` (admin) | Security, compliance, ops |
| **Filesystem subscription** | `filesystem_events` | `GET /api/filesystem-events` (ACL-filtered) | Integrators polling tree changes |

The subscription log holds **`file.*`** and **`folder.*`** event types in one append-only table.

**Retention:** audit and filesystem events use `EVENT_RETENTION_DAYS` (default 90). Probe samples use `PROBES_RETENTION_DAYS` (default 14) in `storage_backend_probes`.

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

### Filesystem event row

Stored in `filesystem_events`. Monotonic `seq` is the poll cursor.

| Field | Type | Notes |
|-------|------|-------|
| `seq` | int | Strictly increasing; allocate via `max(seq)+1` |
| `id` | UUID | |
| `event_type` | string | `file.*` or `folder.*` |
| `created_at` | datetime | |
| `folder_id` | UUID | ACL anchor and filter key |
| `file_id` | UUID \| null | Set for `file.*`; null for `folder.*` |
| `actor_id` | UUID \| null | Defaults to file owner when omitted at emit time |
| `request_id` | string \| null | From `EventContext` when wired |
| `payload` | object | Event-specific body |

**Poll:** `GET /api/filesystem-events?after=<seq>&folder_id=&recursive=&types=&limit=`

Non-admin users only receive events for folders they can **READ**. Admins see all.

**ACL anchor:** for `file.moved` and `folder.moved`, `folder_id` is the **destination** folder (or destination parent for folder moves). Subscribers on the source folder do not see move-out events.

---

## Audit events

### Auth

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `auth.login.succeeded` | succeeded | `POST /api/auth/login` → `auth_mutations.login` | `{ "email": string }` |
| `auth.login.failed` | failed | Same, on bad credentials | `{ "email": string }` |
| `auth.bearer.failed` | failed | Bearer access-key auth on `/api/*` when token is malformed, unknown, revoked, or wrong secret | `{ "reason": "malformed" \| "unknown_key" \| "revoked" \| "invalid_secret" [, "key_id"] }` |
| `auth.logout` | succeeded | `POST /api/auth/logout` → `auth_mutations.logout` | `{ "email": string }` if user known, else `{}` |

Bearer access-key API auth failures are audited; successful bearer calls are not.

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
| `access_key.revoked` | succeeded | `POST /api/access-keys/{key_id}/revoke` | `{ "access_key_id", "key_id", "actor_id" }` — only when newly revoked |
| `access_key.deleted` | succeeded | `DELETE /api/access-keys/{key_id}` | `{ "access_key_id", "key_id", "actor_id" }` |

---

### Folder access (ACL)

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `folder.access.granted` | succeeded | `POST /api/folder-access` (new row) | `{ "access_id", "actor_id", "folder_id", "permissions", "folder_path" }` |
| `folder.access.updated` | succeeded | Same (existing row updated) | Same shape |
| `folder.access.revoked` | succeeded | `DELETE /api/folder-access/{id}` | `{ "access_id", "actor_id", "folder_id", "permissions" }` |

`permissions` is an integer bitfield (`READ=1`, `WRITE=2`, `DELETE=4`, `ENRICH=8`).

---

### Folder control plane (audit summaries)

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `folder.deleted` | succeeded | `DELETE /api/folders/{id}` → `delete_folder` | `{ "deleted_folder_id", "name", "parent_id", "recursive", "descendant_folder_count", "file_count" }` |
| `folder.duplicated` | succeeded | `POST /api/folders/{id}/copy` → `duplicate_folder` | `{ "source_folder_id", "cloned_folder_id", "destination_parent_id", "name", "recursive" }` |
| `folder.preferred_storage_backend.updated` | succeeded | `PATCH /api/folders/{id}` (admin storage preference) | `{ "folder_id", "name", "previous_preferred_storage_backend_id", "preferred_storage_backend_id" }` |

---

### Storage backends (control plane)

| Operation | Status | Trigger | Metadata |
|-----------|--------|---------|----------|
| `storage_backend.created` | succeeded | `POST /api/storage-backends` | `{ "storage_backend_id", "name", "duration_ms", "db_latency_ms" }` |
| `storage_backend.updated` | succeeded | `PATCH /api/storage-backends/{id}` | `{ "storage_backend_id", "name", "changed_fields", "duration_ms", "db_latency_ms" }` |
| `storage_backend.deleted` | succeeded | `DELETE /api/storage-backends/{id}` | `{ "storage_backend_id", "name", "duration_ms", "db_latency_ms" }` |
| `storage_backend.drain_started` | succeeded | `POST /api/storage-backends/{id}/drain` → `drain_storage_backend` | `{ "storage_backend_id", "blob_count" }` |
| `storage_backend.drained` | succeeded | After successful drain | `{ "storage_backend_id", "moved", "skipped", "failed", "scanned" }` |

Manual `POST /api/storage-backends/{id}/probe` writes to `storage_backend_probes` only — no audit row.

---

### Blob purge

**Job:** `purge_dereferenced_blobs`  
**Worker:** `purge_dereferenced_blobs_worker`

| Operation | Status | When | Metadata |
|-----------|--------|------|----------|
| `blob.purged` | succeeded | Remote + DB row deleted | `{ "freed_bytes", "bucket_key" }` |
| `blob.purge_failed` | failed | Exception during purge | `{ "bucket_key", "size_bytes", "error_class", "error_message" }` |

---

### Storage backend probe (batch)

**Job:** `storage_backend_probe`  
**Worker:** `refresh_all_storage_backend_probes_worker`

| Operation | Status | When | Metadata |
|-----------|--------|------|----------|
| `storage_backend.probe_failed` | failed | Probe unreachable or exception | Latency fields or `{ "error_class", "error_message" }` |

Successful probes are stored in `storage_backend_probes` only.

---

### Probe retention trim

**Job:** `trim_storage_backend_probes`

| Operation | Status | Metadata |
|-----------|--------|----------|
| `storage_backend_probe.trimmed` | succeeded | `{ "retention_days", "deleted_rows" }` |

---

### Blob migration (demote / drain / promote)

Per-blob events via `_record_migration_event`. Shared metadata includes `from_storage_backend_id`, `to_storage_backend_id`, `size_bytes`, latencies, `reason`. On failure adds `error_class`, `error_message`.

**Jobs:** `demote_pressured_buckets`, `drain_storage_backend`, `promote_recently_accessed`

| Prefix | Operations |
|--------|------------|
| demote | `blob.demoted`, `blob.demotion_failed`, `blob.demotion_skipped` |
| drain | `blob.drained`, `blob.drain_failed`, `blob.drain_skipped` |
| promote | `blob.promoted`, `blob.promotion_failed`, `blob.promotion_skipped` |

Explicit skip when no destination: `"reason": "no_colder_bucket_with_headroom"` (demote/drain) or `"no_hotter_bucket_with_headroom"` (promote).

---

### Event retention & multipart cleanup

| Operation | Job | Metadata |
|-----------|-----|----------|
| `audit_event.trimmed` | `trim_audit_events` | `{ "retention_days", "deleted_rows" }` |
| `filesystem_event.trimmed` | `trim_filesystem_events` | `{ "retention_days", "deleted_rows" }` |
| `multipart_upload.aborted` | `abort_incomplete_multipart_uploads` | `{ "abort_after_hours", "deleted_rows" }` |

Only emitted when `deleted_rows > 0`.

---

## Filesystem events (subscription log)

Types in `domain/filesystem_events/types.py`. Emitted from `application/control_plane/filesystem_event_emission.py` in the **same transaction** as the mutation.

### `file.created`

| Trigger | Notes |
|---------|-------|
| S3 PUT (new) | `origin: "upload"` |
| S3 multipart complete (new) | `origin: "multipart"` |
| S3 CopyObject | `origin: "copy"`, includes `source_file_id` |
| Folder duplicate | `origin: "duplicate"`, includes `source_file_id` |

**Payload:** `{ name, blob_id, size_bytes, mimetype, extension, meta, origin [, source_file_id] }`

---

### `file.content_updated`

S3 PUT / multipart overwrite when blob changes.

**Payload:** `{ name, blob_id, size_bytes, mimetype, extension, previous_blob_id, meta }`

---

### `file.meta_updated`

`PATCH /api/files/{id}` and bulk meta patch.

**Payload:** `{ name, blob_id, meta }`

---

### `file.renamed`

Rename API; move within same folder with name change.

**Payload:** `{ name, previous_name, blob_id }`

---

### `file.moved`

Move API (cross-folder); bulk move.

**Payload:** `{ name, previous_name, from_folder_id, to_folder_id, blob_id }` — row `folder_id` = `to_folder_id`.

---

### `file.deleted`

File delete API, bulk delete, S3 DeleteObject, recursive folder delete (per file).

**Payload:** `{ name, blob_id }`

---

### `folder.created`

`POST /api/folders`; nested clones during duplicate (not the duplicated root).

**Payload:** `{ name, parent_id }` — row `file_id`: null, `folder_id`: new folder.

---

### `folder.renamed`

`PATCH /api/folders/{id}` name change.

**Payload:** `{ name, previous_name, parent_id }`

---

### `folder.moved`

`PATCH /api/folders/{id}` parent change.

**Payload:** `{ name, from_parent_id, to_parent_id }` — row `folder_id`: destination parent (`to_parent_id`).

---

### `folder.deleted`

`DELETE /api/folders/{id}` (including empty folders). Recursive delete emits **`folder.deleted` per removed folder** (deepest first) plus per-file `file.deleted`.

**Payload:** `{ deleted_folder_id, name, parent_id, recursive, descendant_folder_count, file_count }` — row `folder_id`: nearest ancestor **outside** the delete set (so subscribers with READ on that ancestor still see events after folders are removed).

---

### `folder.duplicated`

`POST /api/folders/{id}/copy` on the new root clone.

**Payload:** `{ name, source_folder_id, destination_parent_id, recursive }`

Nested subfolders emit `folder.created`; files emit `file.created`.

---

### Not in filesystem subscription

| Topic | Log instead |
|-------|-------------|
| `folder.access.*` | Audit |
| `preferred_storage_backend_id` changes | Audit (`folder.preferred_storage_backend.updated`) |

---

## What does not emit events

| Action | Notes |
|--------|-------|
| Storage backend manual probe | `storage_backend_probes` table |
| Successful batch probes | probe table + metrics |
| Blob touch / access time update | `touch_blob_access` |
| Search, list, read, presign | read paths |

---

## Known limitations

| Topic | Detail |
|-------|--------|
| Move-out visibility | `file.moved` / `folder.moved` destination-anchored — source-folder subscribers miss move-out |

---

## Source index

| Area | Files |
|------|-------|
| Audit | `server/ports/audit.py`, `server/infra/db/repositories/audit.py`, `server/infra/db/stores/audit_events.py` |
| Filesystem emit | `server/application/control_plane/filesystem_event_emission.py`, `server/application/gateway/filesystem_event_emission.py` |
| Event types | `server/domain/filesystem_events/types.py` |
| Store / model | `server/infra/db/stores/filesystem_events.py`, `server/infra/db/models.py` (`FilesystemEvent`) |
| Maintenance | `server/infra/maintenance/storage.py`, `server/application/maintenance/retention.py`, `server/workers/maintenance.py` |
| APIs | `server/api/audit_events.py`, `server/api/filesystem_events.py` |
