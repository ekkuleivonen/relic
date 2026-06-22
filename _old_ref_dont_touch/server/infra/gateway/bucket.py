"""Virtual S3 gateway bucket name (wire-format constant, not a storage backend)."""

from domain.exceptions import ResourceNotFound

import settings as S


def gateway_bucket_name() -> str:
    return S.RELIC_GATEWAY_BUCKET


def require_gateway_bucket(bucket_name: str) -> None:
    if bucket_name != gateway_bucket_name():
        raise ResourceNotFound("Storage backend not found")
