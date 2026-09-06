Here's the consolidated table covering all operations the UI and DuckLake will exercise, plus the ones likely to come up in v2/v3:

## Operations

### Uploads & Downloads

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| Upload single file | Gateway (presigned PUT) | Bytes | The dogfooding centerpiece |
| Upload multiple files | Gateway (presigned PUT × N) | Bytes | Each file gets its own presigned URL |
| Upload large file (>8MB) | Gateway (multipart) | Bytes | Required for DuckLake parquet writes |
| Download single file | Gateway (presigned GET) | Bytes | Direct browser-to-gateway |
| Preview / thumbnail | Gateway (presigned GET) | Bytes | Same as download, just inline |
| Stream video / audio | Gateway (presigned GET, ranged) | Bytes | Browser does range reads natively |
| Generate share link | Control plane (issues URL pointing at gateway) | Hybrid | API issues, gateway serves |

### File Operations (Single)

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| Rename file | Control plane (PATCH /files/{id}) | Metadata | Just updates name |
| Move file to different folder | Control plane (POST /files/{id}/move) | Metadata | Re-validates against new folder schema |
| Duplicate file (same folder) | Gateway (CopyObject) | Metadata | Uses S3 verb, metadata-only under the hood |
| Copy file to different folder | Gateway (CopyObject) | Metadata | Same; refcount bump on the Blob |
| Edit file metadata | Control plane (PATCH /files/{id}) | Metadata | Validates against folder schema |
| View file details | Control plane (GET /files/{id}) | Metadata | Rich JSON the UI needs |
| Delete single file | Gateway (DELETE) | Metadata | Preserves dogfooding symmetry with upload |

### File Operations (Bulk)

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| Bulk delete | Control plane (POST /files:bulk-delete) | Metadata | Cleaner errors than S3's DeleteObjects |
| Bulk move | Control plane (POST /files:bulk-move) | Metadata | Transactional; no S3 equivalent anyway |
| Bulk metadata edit | Control plane (POST /files:bulk-update) | Metadata | Apply schema-valid patch across many files |

### Listing & Navigation

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| List folder contents | Control plane (GET /folders/{id}) | Metadata | Richer than S3's ListObjectsV2 |
| Browse folder tree | Control plane (GET /folders/tree) | Metadata | No S3 equivalent |
| Breadcrumbs | Control plane (GET /folders/{id}) | Metadata | Comes with folder details |
| Search by metadata | Control plane (GET /files?meta.x=y) | Metadata | JSONB query; no S3 equivalent |
| Search by name | Control plane (GET /files?name_prefix=...) | Metadata | Indexed lookup |
| Filter by mime type / size / date | Control plane (GET /files?...) | Metadata | All structured filters |

### Folder Operations

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| Create folder | Control plane (POST /folders) | Metadata | No bytes; validates schema inheritance |
| Rename folder | Control plane (PATCH /folders/{id}) | Metadata | Cheap — folder hierarchy is metadata |
| Move folder | Control plane (PATCH /folders/{id}) | Metadata | Updates parent_id |
| Delete folder | Control plane (DELETE /folders/{id}) | Metadata | Cascades; bytes GC'd later via refcount |
| Copy folder (recursive) | Control plane (POST /folders/{id}/copy) | Metadata | The folder-as-versioning primitive |
| Snapshot folder | Control plane (POST /folders/{id}/snapshot) | Metadata | Copy + mark read-only |
| Edit folder schema | Control plane (PATCH /folders/{id}) | Metadata | Validates as superset of parent |
| View folder details | Control plane (GET /folders/{id}) | Metadata | Includes derived stats (file count, size) |

### Permissions & Access

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| List folder ACLs | Control plane (GET /folders/{id}/access) | Metadata | No S3 equivalent in your model |
| Grant folder access | Control plane (POST /folders/{id}/access) | Metadata | |
| Revoke folder access | Control plane (DELETE /folders/{id}/access/{uid}) | Metadata | |
| Check effective permissions | Control plane (GET /folders/{id}?effective=true) | Metadata | Computes via tree walk |

### Admin Operations

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| Manage users | Control plane (/users/_) | Metadata | |
| Manage access keys | Control plane (/access-keys/_) | Metadata | Secret shown once at creation |
| Manage buckets | Control plane (/buckets/*) | Metadata | The backend Bucket entity |
| Probe bucket capacity | Control plane (POST /buckets/{id}/probe) | Metadata | |
| Drain bucket | Control plane (POST /buckets/{id}/drain) | Metadata | Triggers async migration of all blobs |
| Trigger GC | Control plane (POST /blobs/gc) | Metadata | |

### DuckLake / External S3 Clients

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| HEAD object | Gateway | Bytes (metadata) | Required for DuckLake; size/ETag/Last-Modified |
| GET with Range | Gateway | Bytes | Required for parquet column reads |
| PUT (single) | Gateway | Bytes | Required |
| Multipart PUT | Gateway | Bytes | Required for DuckLake parquet outputs |
| DELETE | Gateway | Metadata | Required; must return 204 even if missing |
| ListObjectsV2 | Gateway | Metadata | Required for DuckLake catalog resolution |
| CopyObject | Gateway | Metadata | Useful; not used by DuckLake itself |

### Bytes-Shaped Operations the UI Doesn't Initiate

| Operation | Surface | Nature | Notes |
| --- | --- | --- | --- |
| Pipeline ingestion (Lakeplane) | Gateway | Bytes | Same path as UI uploads |
| External tool uploads (rclone, restic) | Gateway | Bytes | Same path again |
| External tool downloads | Gateway | Bytes | Same path |

## Quick Read of the Breakdown

Counting roughly: about 12 gateway operations, about 30 control plane operations. The gateway handles all bytes plus a small handful of metadata operations that S3 has natural verbs for (DELETE, CopyObject, ListObjectsV2). Everything else flows through the control plane because S3 either has no equivalent or a worse equivalent.

The pattern that emerges:

Bytes are always gateway. No exceptions. Even when "bytes" technically means "metadata-only S3 verb that doesn't actually move bytes" — like CopyObject — it's still the gateway's job because the protocol shape is byte-shaped.

Metadata is usually control plane. Except where S3 has a verb that's exactly the right shape and DuckLake-or-similar will exercise it (DELETE, LIST). Then the gateway has to handle it for compatibility, and the UI uses it too for consistency.

Operations Pithosys invents (folder copy, schema edit, bulk ops, ACLs) are control plane only. The gateway has no equivalent and shouldn't try to grow one.

## The Decision Rule, Restated

When adding a new UI operation, the question is:

- Does it move bytes? → Gateway.
- Does S3 have a verb that's a clean fit and an external tool will use it? → Gateway.
- Otherwise → Control plane.

The middle case is the rare one. Most operations sort cleanly into bytes or metadata.

## What This Implies for Prioritization

The gateway needs to be solid for the operations in the bottom block (DuckLake / external) before anyone outside the UI uses the system. That's your hard compatibility surface. The UI-only gateway operations (single-file delete, copy via CopyObject) are essentially free riders — if HEAD/GET/PUT/DELETE/LIST work for DuckLake, the UI's gateway operations work too.

The control plane is broader but less protocol-sensitive. You can ship CRUD endpoints as the UI needs them; nothing external depends on their exact shape. This is where you get to be opinionated and Pithosys-flavored rather than S3-flavored.

Build the gateway to a high standard once (DuckLake forces this); build the control plane progressively as features land.
