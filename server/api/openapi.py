"""OpenAPI schema customization for Relic API docs."""

from __future__ import annotations

import settings as S
from constants import API_PREFIX
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict, Field

API_DESCRIPTION = """
Relic exposes two HTTP planes:

## JSON control plane (`/api/*`)

Manage users, folders, file metadata, storage backends, and presigned byte access.
Responses are JSON unless noted otherwise.

### Authentication

Use **Authorize** in this UI with either method:

1. **Bearer access key** — paste `key_id:secret` (Swagger adds the `Bearer ` prefix).
   Create keys via `POST /api/access-keys` (admin) or the admin UI.
2. **Session cookie** — call `POST /api/auth/login` first; the `{cookie}` cookie is
   sent automatically on same-origin requests.

Folder permissions apply to non-admin users. Admin-only routes are tagged accordingly.

### Errors

Business rule violations return JSON: `{{"detail": "<message>"}}`

| Status | Meaning |
|--------|---------|
| 400 | Bad request (validation or business rule) |
| 401 | Not authenticated |
| 403 | Forbidden (admin or folder permission) |
| 404 | Resource not found |
| 409 | Conflict |

## S3 gateway (`/s3/*`)

S3-compatible XML API for object bytes. **Path-style only:**
`/s3/{{bucket}}/{{key}}` where `bucket` is a top-level folder name and `key` is nested
folders plus filename (e.g. `/s3/photos/2024/cat.jpg`).

Authentication is **AWS SigV4** (access key signing or presigned URLs).
These routes are **not testable via Authorize** — use `POST /api/uploads/presign*`
to obtain a signed `url` and `headers`, then replay that request manually or in
a REST client.

## Bytes workflow

1. `POST /api/uploads/presign` → signed PUT URL
2. `PUT {{url}}` with returned headers → creates file + blob
3. `GET /api/files/{{id}}` → metadata including `gateway` (`bucket`, `key`, `object_uri`)
4. Stream bytes via `/s3` using one of:
   - `POST /api/uploads/presign-download` → signed GET URL (browser-friendly)
   - Native SigV4 `GET` on `gateway.object_uri` with the same access key (`key_id` + secret)

### Gateway bucket/key mapping

Relic maps the virtual folder tree onto path-style S3 addresses:

| Concept | Rule | Example |
|---------|------|---------|
| Gateway **bucket** | First segment of `FolderRead.path` | `photos` for path `photos/2024` |
| Gateway **key** | Remaining path segments + file name | `2024/cat.jpg` |
| Flat file under bucket folder | Key is the filename only | path `photos`, name `cat.jpg` → key `cat.jpg` |

Every `FileRead` includes a `gateway` object with these fields precomputed.
Physical blob storage (deduplication, backend namespace) is internal — integrators
should use `gateway`, not `blob_id`.

### Service integration (access keys)

One access key, two wire formats:

- **`/api/*`** — `Authorization: Bearer {{key_id}}:{{secret}}`
- **`/s3/*`** — AWS SigV4 `Authorization` header with the same credentials
  (region `relic`, path-style). Do not send Bearer tokens to `/s3`.

Presigned URLs are optional when your client can sign SigV4 requests directly.
""".format(cookie=S.SESSION_COOKIE_NAME)

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "auth",
        "description": (
            "Browser session authentication. `POST /login` sets an HttpOnly session "
            f"cookie (`{S.SESSION_COOKIE_NAME}`). Use **Authorize → BearerAccessKey** "
            "for programmatic access instead."
        ),
    },
    {
        "name": "users",
        "description": "User accounts. **Admin only.**",
    },
    {
        "name": "access-keys",
        "description": (
            "Programmatic credentials. Keys inherit the user's folder permissions for "
            "`/api/*` (Bearer) and `/s3/*` (SigV4). **Admin only** to create; users "
            "can list their own keys."
        ),
    },
    {
        "name": "storage-backends",
        "description": (
            "Physical blob storage (S3 or local filesystem). Encrypted credentials; "
            "placement ranked by probe latency. **Admin only.**"
        ),
    },
    {
        "name": "folders",
        "description": (
            "Virtual filesystem tree. Top-level folder name becomes the S3 bucket "
            "name in `/s3/{bucket}/{key}`. Requires folder permissions."
        ),
    },
    {
        "name": "folder-access",
        "description": (
            "Grant users READ/WRITE/DELETE/ENRICH on folders (bitfield, recursive). "
            "**Admin only.**"
        ),
    },
    {
        "name": "files",
        "description": (
            "File metadata CRUD, search, and bulk ops. Each `FileRead` includes "
            "`gateway` (`bucket`, `key`, `object_uri`) for byte access via `/s3`. "
            "Upload/download can also use presign routes."
        ),
    },
    {
        "name": "filesystem-events",
        "description": (
            "Integrator event stream with monotonic `seq` cursor. Non-admins only "
            "see events for folders they can READ."
        ),
    },
    {
        "name": "uploads",
        "description": (
            "Presigned S3 URLs for upload, download, delete, and copy. Primary way "
            "to move bytes through the gateway from the control plane."
        ),
    },
    {
        "name": "blobs",
        "description": "Blob garbage collection. **Admin only.**",
    },
    {
        "name": "audit-events",
        "description": "Operational audit log. **Admin only.**",
    },
    {
        "name": "s3",
        "description": (
            "S3-compatible XML gateway. **SigV4 authentication only** — not usable "
            "via Swagger Authorize. Test bytes via `/api/uploads/presign*` instead. "
            "Path-style routing: `/s3/{bucket}/{key}`."
        ),
    },
    {
        "name": "health",
        "description": "Liveness and readiness probes. No authentication.",
    },
]

ADMIN_TAGS = frozenset(
    {
        "users",
        "access-keys",
        "storage-backends",
        "folder-access",
        "blobs",
        "audit-events",
    }
)
USER_TAGS = frozenset({"folders", "files", "filesystem-events", "uploads"})
PROTECTED_AUTH_PATHS = frozenset({f"{API_PREFIX}/auth/session"})
PUBLIC_PATHS = frozenset(
    {
        f"{API_PREFIX}/auth/login",
        "/healthz",
        "/readyz",
    }
)

SECURITY_SCHEMES = {
    "BearerAccessKey": {
        "type": "http",
        "scheme": "bearer",
        "description": (
            "Relic access key. In **Authorize**, paste `key_id:secret` "
            "(Swagger adds the `Bearer ` prefix). Not a JWT."
        ),
    },
    "SessionCookie": {
        "type": "apiKey",
        "in": "cookie",
        "name": S.SESSION_COOKIE_NAME,
        "description": (
            "Browser session from `POST /api/auth/login`. Sent automatically on "
            "same-origin `/docs` requests after login."
        ),
    },
}

USER_SECURITY = [{"BearerAccessKey": []}, {"SessionCookie": []}]


class ErrorDetail(BaseModel):
    """Standard error body for domain and validation failures."""

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(description="Human-readable error message.")


COMMON_ERROR_RESPONSES: dict[int, dict] = {
    400: {"model": ErrorDetail, "description": "Bad request"},
    401: {"model": ErrorDetail, "description": "Not authenticated"},
    403: {"model": ErrorDetail, "description": "Forbidden"},
    404: {"model": ErrorDetail, "description": "Resource not found"},
    409: {"model": ErrorDetail, "description": "Conflict"},
}


def _merge_error_responses(operation: dict) -> None:
    existing = set(operation.get("responses", {}))
    merged = dict(operation.get("responses", {}))
    for status_code, response in COMMON_ERROR_RESPONSES.items():
        if status_code in existing:
            continue
        merged[str(status_code)] = {
            "description": response["description"],
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorDetail"},
                },
            },
        }
    operation["responses"] = merged


def _operation_tags(operation: dict) -> set[str]:
    return set(operation.get("tags") or [])


def _path_needs_user_security(path: str, operation: dict) -> bool:
    if path in PUBLIC_PATHS:
        return False
    if path in PROTECTED_AUTH_PATHS:
        return True
    tags = _operation_tags(operation)
    return bool(tags & (ADMIN_TAGS | USER_TAGS))


def configure_openapi(app: FastAPI) -> None:
    """Attach security schemes, error responses, and tag-based auth to the schema."""

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {}).update(SECURITY_SCHEMES)
        components.setdefault("schemas", {})["ErrorDetail"] = ErrorDetail.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )

        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                    "trace",
                }:
                    continue
                if not isinstance(operation, dict):
                    continue
                if _path_needs_user_security(path, operation):
                    operation["security"] = USER_SECURITY
                    _merge_error_responses(operation)

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
