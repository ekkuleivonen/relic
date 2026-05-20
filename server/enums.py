import enum


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
    ENRICH = 8  # for patching file meta


class EventStatus(enum.StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class HealthStatus(enum.StrEnum):
    OK = "ok"
    FAILED = "failed"


class StorageKind(enum.StrEnum):
    S3 = "s3"
    FILESYSTEM = "filesystem"
