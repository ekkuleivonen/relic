import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from managers.exceptions import ConflictError, ResourceNotFound
from models import User
from utils.passwords import hash_password


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.email)).all())


def create_user(db: Session, data: dict) -> User:
    ensure_email_available(db, data["email"])
    user = User(
        name=data["name"],
        email=data["email"],
        password_hash=hash_password(data["password"]),
        role=data["role"],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ResourceNotFound("User not found")

    return user


def update_user(db: Session, user_id: uuid.UUID, data: dict) -> User:
    user = get_user(db, user_id)

    if "email" in data and data["email"] != user.email:
        ensure_email_available(db, data["email"], excluding_user_id=user.id)
        user.email = data["email"]

    if "name" in data:
        user.name = data["name"]
    if "role" in data:
        user.role = data["role"]
    if "password" in data:
        user.password_hash = hash_password(data["password"])

    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: uuid.UUID) -> None:
    user = get_user(db, user_id)
    db.delete(user)
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
