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
    ENRICH = 8  # for parsers/transformers updating meta


class BucketTier(enum.IntEnum):
    HOT = 1
    WARM = 2
    COLD = 3
    FROZEN = 4
