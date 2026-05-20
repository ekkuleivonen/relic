import uuid

from application.context import EventContext
from infra.db.stores.access_keys import (
    AccessKeyRow,
    CreatedAccessKey,
    generate_key_id,
    generate_secret_access_key,
)
from application.uow import UnitOfWork
from infra.db.models import AccessKey
from utils.logging import get_logger

log = get_logger(__name__)


def create_access_key(
    uow: UnitOfWork,
    *,
    actor_id: uuid.UUID,
    name: str,
    event_context: EventContext | None = None,
) -> CreatedAccessKey:
    user = uow.users.get(actor_id)
    key_id = generate_key_id()
    secret_access_key = generate_secret_access_key()
    access_key = AccessKey(
        actor_id=user.id,
        name=name,
        key_id=key_id,
        secret_access_key=secret_access_key,
    )
    uow.access_keys.add(access_key)
    uow.audit.record(
        operation="access_key.created",
        event_context=event_context,
        metadata={
            "access_key_id": str(access_key.id),
            "key_id": access_key.key_id,
            "actor_id": str(access_key.actor_id),
            "name": access_key.name,
        },
    )
    uow.cache.invalidate_access_key(uow.session, access_key.key_id)
    log.info(
        "access_key_create",
        access_key_id=str(access_key.id),
        key_id=access_key.key_id,
        actor_id=str(user.id),
    )
    return CreatedAccessKey(
        row=AccessKeyRow(access_key=access_key, user=user),
        secret_access_key=secret_access_key,
    )


def revoke_access_key(
    uow: UnitOfWork,
    key_id: str,
    *,
    event_context: EventContext | None = None,
) -> AccessKeyRow:
    row = uow.access_keys.get_by_key_id(key_id)
    if row.access_key.revoked_at is None:
        uow.access_keys.revoke(row.access_key)
        uow.audit.record(
            operation="access_key.revoked",
            event_context=event_context,
            metadata={
                "access_key_id": str(row.access_key.id),
                "key_id": row.access_key.key_id,
                "actor_id": str(row.access_key.actor_id),
            },
        )
        uow.cache.invalidate_access_key(uow.session, row.access_key.key_id)
        log.info(
            "access_key_revoke",
            access_key_id=str(row.access_key.id),
            key_id=row.access_key.key_id,
            actor_id=str(row.access_key.actor_id),
        )
    return row


def delete_access_key(
    uow: UnitOfWork,
    key_id: str,
    *,
    event_context: EventContext | None = None,
) -> None:
    row = uow.access_keys.get_by_key_id(key_id)
    uow.audit.record(
        operation="access_key.deleted",
        event_context=event_context,
        metadata={
            "access_key_id": str(row.access_key.id),
            "key_id": row.access_key.key_id,
            "actor_id": str(row.access_key.actor_id),
        },
    )
    uow.access_keys.delete(row.access_key)
    uow.cache.invalidate_access_key(uow.session, key_id)
    log.info(
        "access_key_delete",
        access_key_id=str(row.access_key.id),
        key_id=row.access_key.key_id,
        actor_id=str(row.access_key.actor_id),
    )
