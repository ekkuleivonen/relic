"""Object-storage capability checks (pure; no I/O)."""

import settings as S
from domain.exceptions import BadRequestError
from ports.object_storage import StorageCapabilities


def enforce_max_object_bytes(*, size_bytes: int) -> None:
    if size_bytes > S.MAX_OBJECT_BYTES:
        raise BadRequestError(
            f"Object size {size_bytes} exceeds maximum allowed size "
            f"{S.MAX_OBJECT_BYTES} bytes"
        )


def enforce_single_put_size(*, caps: StorageCapabilities, size_bytes: int) -> None:
    limit = caps.max_single_put_bytes
    if limit is not None and size_bytes > limit:
        raise BadRequestError(
            f"Object size {size_bytes} exceeds maximum single PUT size {limit} "
            "for this storage backend"
        )


def enforce_multipart(*, caps: StorageCapabilities) -> None:
    if not caps.multipart:
        raise BadRequestError(
            "Multipart uploads are not supported for this storage backend"
        )


def enforce_server_side_copy(*, caps: StorageCapabilities) -> None:
    if not caps.server_side_copy:
        raise BadRequestError(
            "Server-side copy is not supported for this storage backend"
        )
