import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from managers.exceptions import ResourceNotFound
from models import AccessKey, User
from services.users import get_user
from utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class AccessKeyRow:
    access_key: AccessKey
    user: User


@dataclass(frozen=True)
class CreatedAccessKey:
    row: AccessKeyRow
    secret_access_key: str


def list_access_keys(db: Session) -> list[AccessKeyRow]:
    rows = db.execute(
        select(AccessKey, User)
        .join(User, User.id == AccessKey.user_id)
        .order_by(User.email, AccessKey.created_at.desc())
    ).all()
    return [AccessKeyRow(access_key=row.AccessKey, user=row.User) for row in rows]


def create_access_key(
    db: Session,
    *,
    user_id: uuid.UUID,
    name: str,
) -> CreatedAccessKey:
    user = get_user(db, user_id)
    key_id = generate_key_id()
    secret_access_key = generate_secret_access_key()
    access_key = AccessKey(
        user_id=user.id,
        name=name,
        key_id=key_id,
        secret_hash=hash_secret(secret_access_key),
    )
    db.add(access_key)
    db.commit()
    db.refresh(access_key)
    log.info(
        "access_key_create",
        access_key_id=str(access_key.id),
        key_id=access_key.key_id,
        user_id=str(user.id),
    )
    return CreatedAccessKey(
        row=AccessKeyRow(access_key=access_key, user=user),
        secret_access_key=secret_access_key,
    )


def get_access_key_by_key_id(db: Session, key_id: str) -> AccessKeyRow:
    row = db.execute(
        select(AccessKey, User)
        .join(User, User.id == AccessKey.user_id)
        .where(AccessKey.key_id == key_id)
    ).first()
    if not row:
        raise ResourceNotFound("Access key not found")

    return AccessKeyRow(access_key=row.AccessKey, user=row.User)


def revoke_access_key(db: Session, key_id: str) -> AccessKeyRow:
    row = get_access_key_by_key_id(db, key_id)
    if row.access_key.revoked_at is None:
        row.access_key.revoked_at = dt.datetime.now(dt.UTC)
        db.commit()
        db.refresh(row.access_key)
        log.info(
            "access_key_revoke",
            access_key_id=str(row.access_key.id),
            key_id=row.access_key.key_id,
            user_id=str(row.access_key.user_id),
        )

    return row


def delete_access_key(db: Session, key_id: str) -> None:
    row = get_access_key_by_key_id(db, key_id)
    db.delete(row.access_key)
    db.commit()
    log.info(
        "access_key_delete",
        access_key_id=str(row.access_key.id),
        key_id=row.access_key.key_id,
        user_id=str(row.access_key.user_id),
    )


def generate_key_id() -> str:
    return f"RK{secrets.token_hex(16).upper()}"


def generate_secret_access_key() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(secret_access_key: str) -> bytes:
    return hashlib.sha256(secret_access_key.encode()).digest()
