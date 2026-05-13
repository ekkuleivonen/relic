import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.exceptions import ConflictError, ResourceNotFound
from models import File, User
from services.audit_events import create_audit_event
from services.event_context import EventContext
from utils.passwords import hash_password


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.email)).all())


def create_user(
    db: Session, data: dict, *, event_context: EventContext | None = None
) -> User:
    ensure_email_available(db, data["email"])
    user = User(
        name=data["name"],
        email=data["email"],
        password_hash=hash_password(data["password"]),
        role=data["role"],
    )
    db.add(user)
    db.flush()
    if event_context is not None:
        create_audit_event(
            db,
            operation="user.created",
            actor_id=event_context.actor_id,
            request_id=event_context.request_id,
            metadata={
                "user_id": str(user.id),
                "email": user.email,
                "role": int(user.role),
            },
        )
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ResourceNotFound("User not found")

    return user


def update_user(
    db: Session,
    user_id: uuid.UUID,
    data: dict,
    *,
    event_context: EventContext | None = None,
) -> User:
    user = get_user(db, user_id)
    changed_fields = sorted(data)

    if "email" in data and data["email"] != user.email:
        ensure_email_available(db, data["email"], excluding_user_id=user.id)
        user.email = data["email"]

    if "name" in data:
        user.name = data["name"]
    if "role" in data:
        user.role = data["role"]
    if "password" in data:
        user.password_hash = hash_password(data["password"])

    db.flush()
    if event_context is not None:
        create_audit_event(
            db,
            operation="user.updated",
            actor_id=event_context.actor_id,
            request_id=event_context.request_id,
            metadata={
                "user_id": str(user.id),
                "email": user.email,
                "changed_fields": changed_fields,
            },
        )
    db.commit()
    db.refresh(user)
    return user


def delete_user(
    db: Session, user_id: uuid.UUID, *, event_context: EventContext | None = None
) -> None:
    user = get_user(db, user_id)
    uploaded_file_id = db.scalar(select(File.id).where(File.actor_id == user.id).limit(1))
    if uploaded_file_id is not None:
        raise ConflictError("Cannot delete user with uploaded files")

    metadata = {"user_id": str(user.id), "email": user.email}
    actor_id = event_context.actor_id if event_context else None
    if actor_id == user.id:
        actor_id = None
    db.delete(user)
    if event_context is not None:
        create_audit_event(
            db,
            operation="user.deleted",
            actor_id=actor_id,
            request_id=event_context.request_id,
            metadata=metadata,
        )
    db.commit()


def ensure_email_available(
    db: Session,
    email: str,
    *,
    excluding_user_id: uuid.UUID | None = None,
) -> None:
    existing = db.scalar(select(User).where(User.email == email))
    if existing and existing.id != excluding_user_id:
        raise ConflictError("User email already exists")
