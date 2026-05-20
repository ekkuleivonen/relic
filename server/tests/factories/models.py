import datetime as dt

import factory
from enums import EventStatus, Permission, StorageKind, UserRole
from infra.db.models import (
    AccessKey,
    AuditEvent,
    Blob,
    Bucket,
    BucketProbe,
    Folder,
    FolderAccess,
    User,
)
from utils.passwords import hash_password


class BucketFactory(factory.Factory):
    class Meta:
        model = Bucket

    name = factory.Sequence(lambda n: f"garage-{n}")
    endpoint = "http://garage-hot:3900"
    region = "garage"
    bucket = "blobs"
    key_id = factory.Sequence(lambda n: f"GK{n:024d}")
    secret_access_key = factory.Sequence(lambda n: f"secret-{n}")
    max_size_bytes = 1_000_000_000
    storage_kind = StorageKind.S3


class BucketProbeFactory(factory.Factory):
    class Meta:
        model = BucketProbe

    bucket_id = None
    observed_at = factory.LazyFunction(lambda: dt.datetime.now(dt.UTC))
    success = True
    put_ms = 10
    head_ms = 10
    get_ms = 10
    delete_ms = 10


class BlobFactory(factory.Factory):
    class Meta:
        model = Blob

    bucket_id = None
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
    preferred_bucket_id = None


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
    bucket_id = None
    blob_id = None
    duration_ms = None
    meta = factory.LazyFunction(dict)
    created_at = factory.LazyFunction(lambda: dt.datetime.now(dt.UTC))
    updated_at = factory.LazyFunction(lambda: dt.datetime.now(dt.UTC))
