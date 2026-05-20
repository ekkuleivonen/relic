"""S3 ListBuckets / ListObjectsV2 use cases."""

from application.uow import UnitOfWork
from infra.gateway import object_listing
from infra.gateway.object_listing import BucketListingItem
from ports.entities import User


def list_visible_buckets(uow: UnitOfWork, user: User) -> list[BucketListingItem]:
    return object_listing.list_visible_buckets(uow.session, user)


def require_visible_bucket(uow: UnitOfWork, user: User, bucket_name: str):
    return object_listing.require_visible_bucket(uow.session, user, bucket_name)


def list_objects_v2(
    uow: UnitOfWork,
    *,
    user: User,
    bucket_name: str,
    prefix: str = "",
    delimiter: str | None = None,
    max_keys: int,
    continuation_token: str | None = None,
    start_after: str | None = None,
):
    return object_listing.list_objects_v2(
        uow.session,
        user,
        bucket_name=bucket_name,
        prefix=prefix,
        delimiter=delimiter,
        max_keys=max_keys,
        continuation_token=continuation_token,
        start_after=start_after,
    )
