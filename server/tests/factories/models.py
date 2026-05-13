import factory

from models import (
    AccessKey,
    AuditEvent,
    Blob,
    Bucket,
    FileEvent,
    Folder,
    FolderAccess,
    PROCESSOR_SOURCE_SEED,
    Processor,
    User,
)
from schema_plan import BucketTier, Permission, UserRole
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
    tier = BucketTier.HOT
    max_size_bytes = 1_000_000_000


class BlobFactory(factory.Factory):
    class Meta:
        model = Blob

    bucket_id = None
    bucket_key = factory.Sequence(lambda n: f"objects/{n}")
    content_hash = factory.Sequence(lambda n: n.to_bytes(32, "big"))
    size_bytes = 1
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

    user_id = None
    name = factory.Sequence(lambda n: f"access-key-{n}")
    key_id = factory.Sequence(lambda n: f"RK{n:032X}")
    secret_hash = factory.Sequence(lambda n: n.to_bytes(32, "big"))
    last_used_at = None
    revoked_at = None


class FolderFactory(factory.Factory):
    class Meta:
        model = Folder

    name = factory.Sequence(lambda n: f"folder-{n}")
    parent_id = None
    cooldown_days = None
    min_tier = BucketTier.HOT


class FolderAccessFactory(factory.Factory):
    class Meta:
        model = FolderAccess

    user_id = None
    folder_id = None
    permissions = int(Permission.READ)


class AuditEventFactory(factory.Factory):
    class Meta:
        model = AuditEvent

    operation = factory.Sequence(lambda n: f"operation-{n}")
    status = "succeeded"
    actor_user_id = None
    request_id = factory.Sequence(lambda n: f"req-{n}")
    file_ids = factory.LazyFunction(list)
    folder_ids = factory.LazyFunction(list)
    blob_ids = factory.LazyFunction(list)
    meta = factory.LazyFunction(dict)


class FileEventFactory(factory.Factory):
    class Meta:
        model = FileEvent

    offset = factory.Sequence(lambda n: n + 1)
    schema_version = 1
    event_type = factory.Sequence(lambda n: f"file.event.{n}")
    status = "succeeded"
    actor_user_id = None
    request_id = factory.Sequence(lambda n: f"req-{n}")
    idempotency_key = None
    file_id = None
    folder_id = None
    payload = factory.LazyFunction(dict)


class ProcessorFactory(factory.Factory):
    class Meta:
        model = Processor

    name = factory.Sequence(lambda n: f"processor-{n}")
    kind = "meta_extract"
    enabled = True
    source = PROCESSOR_SOURCE_SEED
    subscribed_event_types = factory.LazyFunction(
        lambda: ["file.created", "file.updated"]
    )
    config = factory.LazyFunction(dict)
    last_committed_offset = 0
    last_committed_at = None
    last_failed_event_id = None
    last_failed_at = None
    last_error_class = None
    last_error_message = None
