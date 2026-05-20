import datetime as dt

import factory
from enums import EventStatus, Permission, StorageBackendKind, UserRole
from infra.db.models import (
    AccessKey,
    AuditEvent,
    Blob,
    StorageBackend,
    StorageBackendProbe,
    Folder,
    FolderAccess,
    User,
)
from utils.passwords import hash_password


class StorageBackendFactory(factory.Factory):
    class Meta:
        model = StorageBackend

    name = factory.Sequence(lambda n: f"garage-{n}")
    endpoint = "http://garage-hot:3900"
    region = "garage"
    namespace = "blobs"
    key_id = factory.Sequence(lambda n: f"GK{n:024d}")
    secret_access_key = factory.Sequence(lambda n: f"secret-{n}")
    max_size_bytes = 1_000_000_000
    kind = StorageBackendKind.S3


class StorageBackendProbeFactory(factory.Factory):
    class Meta:
        model = StorageBackendProbe

    storage_backend_id = None
    observed_at = factory.LazyFunction(lambda: dt.datetime.now(dt.UTC))
    success = True
    put_ms = 10
    head_ms = 10
    get_ms = 10
    delete_ms = 10


class BlobFactory(factory.Factory):
    class Meta:
        model = Blob

    storage_backend_id = None
    bucket_key = factory.Sequence(lambda n: f"objects/{n}")
    content_hash = factory.Sequence(lambda n: n.to_bytes(32, "big"))
    size_bytes = 1
    mimetype = "application/octet-stream"
    extension = ""
    refcount = 1


class UserFactory(factory.Factory):
    class Meta:
        model = User

    name = factory.Sequence(lambda n: f"User {n}")
    email = factory.Sequence(lambda n: f"user-{n}@relic.local")
    password_hash = factory.LazyFunction(lambda: hash_password("password"))
    role = UserRole.USER


class AccessKeyFactory(factory.Factory):
    class Meta:
        model = AccessKey

    actor_id = None
    name = factory.Sequence(lambda n: f"access-key-{n}")
    key_id = factory.Sequence(lambda n: f"RK{n:032X}")
    secret_access_key = factory.Sequence(lambda n: f"secret-{n}")
    last_used_at = None
    revoked_at = None


class FolderFactory(factory.Factory):
    class Meta:
        model = Folder

    name = factory.Sequence(lambda n: f"folder-{n}")
    parent_id = None
    preferred_storage_backend_id = None


class FolderAccessFactory(factory.Factory):
    class Meta:
        model = FolderAccess

    actor_id = None
    folder_id = None
    permissions = int(Permission.READ)


class AuditEventFactory(factory.Factory):
    class Meta:
        model = AuditEvent

    operation = factory.Sequence(lambda n: f"audit.operation.{n}")
    status = EventStatus.SUCCEEDED
    actor_id = None
    request_id = None
    job = None
    batch_id = None
    storage_backend_id = None
    blob_id = None
    duration_ms = None
    meta = factory.LazyFunction(dict)
    created_at = factory.LazyFunction(lambda: dt.datetime.now(dt.UTC))
    updated_at = factory.LazyFunction(lambda: dt.datetime.now(dt.UTC))
