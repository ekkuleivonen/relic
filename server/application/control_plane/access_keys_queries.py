"""Access key read queries (admin control plane)."""

from application.uow import UnitOfWork
from infra.db.stores import access_keys
from infra.db.stores.access_keys import AccessKeyRow, CreatedAccessKey


def list_access_keys(uow: UnitOfWork) -> list[AccessKeyRow]:
    return access_keys.list_access_keys(uow.session)


def get_access_key_by_key_id(uow: UnitOfWork, key_id: str) -> AccessKeyRow:
    return access_keys.get_access_key_by_key_id(uow.session, key_id)
