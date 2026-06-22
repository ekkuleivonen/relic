import uuid

from application.context import EventContext
from application.uow import UnitOfWork
from domain.exceptions import ConflictError
from ports.entities import User
from utils.logging import get_logger
from utils.passwords import hash_password

log = get_logger(__name__)


def create_user(
    uow: UnitOfWork,
    data: dict,
    *,
    event_context: EventContext | None = None,
) -> User:
    uow.users.ensure_email_available(data["email"])
    user = User(
        name=data["name"],
        email=data["email"],
        password_hash=hash_password(data["password"]),
        role=data["role"],
    )
    uow.users.add(user)
    uow.audit.record(
        operation="user.created",
        event_context=event_context,
        metadata={
            "user_id": str(user.id),
            "email": user.email,
            "role": int(user.role),
        },
    )
    uow.users.save(user)
    log.info("user_create", user_id=str(user.id), email=user.email)
    return user


def update_user(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    data: dict,
    *,
    event_context: EventContext | None = None,
) -> User:
    user = uow.users.get(user_id)
    changed_fields = sorted(data)

    if "email" in data and data["email"] != user.email:
        uow.users.ensure_email_available(data["email"], excluding_user_id=user.id)
        user.email = data["email"]
    if "name" in data:
        user.name = data["name"]
    if "role" in data:
        user.role = data["role"]
    if "password" in data:
        user.password_hash = hash_password(data["password"])

    uow.audit.record(
        operation="user.updated",
        event_context=event_context,
        metadata={
            "user_id": str(user.id),
            "email": user.email,
            "changed_fields": changed_fields,
        },
    )
    uow.users.save(user)
    log.info("user_update", user_id=str(user.id), email=user.email)
    return user


def delete_user(
    uow: UnitOfWork,
    user_id: uuid.UUID,
    *,
    event_context: EventContext | None = None,
) -> None:
    user = uow.users.get(user_id)
    if uow.users.has_uploaded_files(user.id):
        raise ConflictError("Cannot delete user with uploaded files")

    metadata = {"user_id": str(user.id), "email": user.email}
    uow.users.delete(user)
    uow.audit.record(
        operation="user.deleted",
        event_context=event_context,
        metadata=metadata,
    )
    log.info("user_delete", user_id=str(user.id), email=user.email)
