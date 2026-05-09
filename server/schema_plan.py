import datetime as dt
import enum
import uuid

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

ROOT_FOLDER_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "FolderSchema",
    "type": "object",
    "properties": {
        "original_name": {"type": "string"},
        "file_size": {"type": "integer", "minimum": 0},
        "mime_type": {"type": "string"},
        "extension": {"type": "string"},
    },
    "required": ["original_name", "file_size", "mime_type", "extension"],
    "additionalProperties": True,  # child folders extend with more fields
}


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------


class UserRole(enum.IntEnum):
    USER = 1
    ADMIN = 2


class Permission(enum.IntFlag):
    """
    Bitfield. Compose with |. Check with &.
        e.g. Permission.READ | Permission.WRITE
    """

    READ = 1
    WRITE = 2
    DELETE = 4
    ENRICH = 8  # for parsers/transformers updating meta
    ADMIN = 16  # manage folder itself: schema, ACLs, child folders


class StorageTier(enum.IntEnum):
    HOT = 1
    WARM = 2
    COLD = 3
    FROZEN = 4


# -----------------------------------------------------------------------------
# Entities
# -----------------------------------------------------------------------------


class User:
    """
    Users are the entities that interact with the system.
    Auth is intentionally minimal for now - swap to OIDC/Authentik later.
    """

    id: uuid.UUID
    name: str
    email: str
    password_hash: str  # argon2 or bcrypt; temporary internal auth
    role: UserRole
    created_at: dt.datetime
    updated_at: dt.datetime


class AccessKey:
    """
    S3 access keys for SigV4 verification at the gateway.
    Each key is owned by a user; permissions follow the user's folder ACLs.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    name: str  # human-friendly label
    key_id: str  # the public part (used as access key id)
    secret_hash: bytes  # hash of the secret; secret only shown once at creation
    created_at: dt.datetime
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None


class Storage:
    """
    Real underlying S3-compatible buckets. The connectors to remote storage.

    Routing algorithm (see also: Folder.cooldown_*):
      1. Filter to storages with capacity headroom (used < capacity * 0.7)
      2. Among those, prefer the tier matching the file's current "warmth"
         (driven by Folder.cooldown_* policy and File.accessed_at)
      3. Tiebreak by lowest probed latency
    """

    id: uuid.UUID
    name: str
    endpoint: str
    region: str
    secret_ref: str  # K8s secret name holding key_id + secret_access_key

    tier: StorageTier

    storage_capacity: int  # bytes; updated on cron
    storage_used: int  # bytes; updated on cron
    storage_latency_ms: int  # updated on cron via probe
    headroom_pct: int  # how much buffer to keep free; default 30

    created_at: dt.datetime
    updated_at: dt.datetime


class Blob:
    """
    Physical bytes stored in a Storage. Immutable.
    Identified by content_hash; storage_key is implementation detail.
    refcount < 1 means hard delete (YAGNI tombstones for now).
    """

    id: uuid.UUID
    storage_id: uuid.UUID
    storage_key: str
    content_hash: bytes  # raw SHA-256, 32 bytes
    refcount: int  # denormalized; hits 0 -> physical delete + row removal
    created_at: dt.datetime
    accessed_at: dt.datetime  # updated lazily from access events


class File:
    """
    Logical reference to a Blob, living inside exactly one Folder.
    Mutable, throwaway. Same Blob can be referenced by many Files (free copy).
    """

    id: uuid.UUID
    folder_id: uuid.UUID  # never null; root folder is seeded at startup
    blob_id: uuid.UUID
    name: str
    meta: dict  # JSONB; validated against folder.schema at write time
    schema_version_validated: int | None  # which folder schema version passed
    accessed_at: dt.datetime  # updated lazily; drives storage demotion
    created_at: dt.datetime
    updated_at: dt.datetime


class Folder:
    """
    Virtual filesystem nodes. Attach points for ACLs and metadata schema.
    Schemas are extend-only down the tree (additionalProperties allowed).

    Storage policy is access-age-driven rather than tier-locked:
    files cooler than `cooldown_days` get demoted one tier on the next sweep.
    Set cooldown_days = None to disable demotion (sticky-hot).
    """

    id: uuid.UUID
    parent_id: uuid.UUID | None  # only the root has None
    name: str
    schema: dict  # JSON Schema; root seeded with ROOT_FOLDER_SCHEMA

    # Storage policy
    cooldown_days: int | None  # demote files untouched for > N days; None = sticky
    min_tier: StorageTier  # don't demote below this tier (e.g., 3 = never archive)

    created_at: dt.datetime
    updated_at: dt.datetime


class FolderAccess:
    """
    Per-user permissions on a folder. Inheritance is computed at evaluation
    time by walking up parent_id; not stored. Effective permissions on folder F
    for user U = union of all FolderAccess rows from F up to root.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    folder_id: uuid.UUID
    permissions: Permission
    created_at: dt.datetime
    updated_at: dt.datetime


# -----------------------------------------------------------------------------
# Constraints we'll need at the DB layer (notes for migration time)
# -----------------------------------------------------------------------------
#
# folders:
#   UNIQUE (parent_id, name) NULLS NOT DISTINCT
#     -> prevents two folders with same name under same parent;
#        also prevents two roots
#
# files:
#   UNIQUE (folder_id, name)
#     -> S3-style: keys are unique within their folder
#
# blobs:
#   UNIQUE (content_hash)
#     -> dedup invariant; one row per unique content
#   INDEX (storage_id) for tiering sweeps
#   INDEX (accessed_at) for cooldown queries -- maybe; revisit if hot
#
# files:
#   INDEX (blob_id) for refcount maintenance
#   INDEX (folder_id) for folder listings
#   GIN INDEX (meta) -- defer until query patterns demand it
#
# access_keys:
#   UNIQUE (key_id)
#     -> SigV4 lookup is by key_id
