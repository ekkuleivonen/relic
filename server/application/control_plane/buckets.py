"""Bucket read models — mutations use ``bucket_mutations`` on UoW."""

import uuid
from typing import Any

from application.uow import UnitOfWork
from ports.entities import Bucket
from infra.db.stores import bucket_reads

def list_buckets(uow: UnitOfWork) -> list[Bucket]:
    return bucket_reads.list_buckets(uow.session)


def list_bucket_reads(uow: UnitOfWork) -> list[dict[str, Any]]:
    return bucket_reads.list_bucket_reads(uow.session)


def get_bucket(uow: UnitOfWork, bucket_id: uuid.UUID) -> Bucket:
    return uow.buckets.get(bucket_id)


def get_bucket_read(uow: UnitOfWork, bucket_id: uuid.UUID) -> dict[str, Any]:
    return bucket_reads.get_bucket_read(uow.session, bucket_id)
