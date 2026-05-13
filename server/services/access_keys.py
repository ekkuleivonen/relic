import datetime as dt
import secrets
import uuid
from dataclasses import dataclass

import settings as S
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.exceptions import ResourceNotFound
from models import AccessKey, User
from services.audit_events import create_audit_event
from services.event_context import EventContext
from services.s3_hotpath_cache import (
    TtlCacheEntry,
    engine_cache_key,
    get_ttl,
    monotonic_now,
    set_ttl,
)
from services.users import get_user
from utils.logging import get_logger

log = get_logger(__name__)

_ACTIVE_ACCESS_KEY_CACHE: dict[tuple[int, str], TtlCacheEntry] = {}
_LAST_USED_WRITE_CACHE: dict[tuple[int, uuid.UUID], TtlCacheEntry] = {}


@dataclass(frozen=True)
class AccessKeyRow:
    access_key: AccessKey
    user: User


@dataclass(frozen=True)
class CreatedAccessKey:
    row: AccessKeyRow
    secret_access_key: str


@dataclass(frozen=True)
class ActiveAccessKeyCredentials:
    access_key_id: uuid.UUID
    user_id: uuid.UUID
    secret_access_key: str


def list_access_keys(db: Session) -> list[AccessKeyRow]:
    rows = db.execute(
        select(AccessKey, User)
        .join(User, User.id == AccessKey.actor_id)
        .order_by(User.email, AccessKey.created_at.desc())
    ).all()
    return [AccessKeyRow(access_key=row.AccessKey, user=row.User) for row in rows]


def create_access_key(
    db: Session,
    *,
    actor_id: uuid.UUID,
    name: str,
    event_context: EventContext | None = None,
) -> CreatedAccessKey:
    user = get_user(db, actor_id)
    key_id = generate_key_id()
    secret_access_key = generate_secret_access_key()
    access_key = AccessKey(
        actor_id=user.id,
        name=name,
        key_id=key_id,
        secret_access_key=secret_access_key,
    )
    db.add(access_key)
    db.flush()
    if event_context is not None:
        create_audit_event(
            db,
            operation="access_key.created",
            actor_id=event_context.actor_id,
            request_id=event_context.request_id,
            metadata={
                "access_key_id": str(access_key.id),
                "key_id": access_key.key_id,
                "actor_id": str(access_key.actor_id),
                "name": access_key.name,
            },
        )
    db.commit()
    db.refresh(access_key)
    clear_access_key_hotpath_cache(db, access_key.key_id)
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


def get_access_key_by_key_id(db: Session, key_id: str) -> AccessKeyRow:
    row = db.execute(
        select(AccessKey, User)
        .join(User, User.id == AccessKey.actor_id)
        .where(AccessKey.key_id == key_id)
    ).first()
    if not row:
        raise ResourceNotFound("Access key not found")

    return AccessKeyRow(access_key=row.AccessKey, user=row.User)


def get_active_access_key_by_key_id(db: Session, key_id: str) -> AccessKeyRow:
    row = get_access_key_by_key_id(db, key_id)
    if row.access_key.revoked_at is not None:
        raise ResourceNotFound("Access key not found")
    return row


def get_active_access_key_credentials_by_key_id(
    db: Session, key_id: str
) -> ActiveAccessKeyCredentials:
    cache_key = (engine_cache_key(db), key_id)
    cached = get_ttl(_ACTIVE_ACCESS_KEY_CACHE, cache_key)
    if cached is not None:
        return cached

    row = get_active_access_key_by_key_id(db, key_id)
    credentials = ActiveAccessKeyCredentials(
        access_key_id=row.access_key.id,
        user_id=row.user.id,
        secret_access_key=row.access_key.secret_access_key,
    )
    return set_ttl(
        _ACTIVE_ACCESS_KEY_CACHE,
        cache_key,
        credentials,
        ttl_seconds=S.S3_ACCESS_KEY_CACHE_TTL_SECONDS,
    )


def mark_access_key_used(db: Session, access_key: AccessKey) -> None:
    mark_access_key_used_by_id(db, access_key.id)


def mark_access_key_used_by_id(db: Session, access_key_id: uuid.UUID) -> None:
    cache_key = (engine_cache_key(db), access_key_id)
    if get_ttl(_LAST_USED_WRITE_CACHE, cache_key) is not None:
        return

    access_key = db.get(AccessKey, access_key_id)
    if access_key is None:
        return

    access_key.last_used_at = dt.datetime.now(dt.UTC)
    db.commit()
    set_ttl(
        _LAST_USED_WRITE_CACHE,
        cache_key,
        True,
        ttl_seconds=S.S3_ACCESS_KEY_LAST_USED_DEBOUNCE_SECONDS,
        now=monotonic_now(),
    )


def clear_access_key_hotpath_cache(db: Session, key_id: str | None = None) -> None:
    engine_key = engine_cache_key(db)
    for cache_key in list(_ACTIVE_ACCESS_KEY_CACHE):
        if cache_key[0] == engine_key and (key_id is None or cache_key[1] == key_id):
            _ACTIVE_ACCESS_KEY_CACHE.pop(cache_key, None)


def revoke_access_key(
    db: Session, key_id: str, *, event_context: EventContext | None = None
) -> AccessKeyRow:
    row = get_access_key_by_key_id(db, key_id)
    if row.access_key.revoked_at is None:
        row.access_key.revoked_at = dt.datetime.now(dt.UTC)
        db.flush()
        if event_context is not None:
            create_audit_event(
                db,
                operation="access_key.revoked",
                actor_id=event_context.actor_id,
                request_id=event_context.request_id,
                metadata={
                    "access_key_id": str(row.access_key.id),
                    "key_id": row.access_key.key_id,
                    "actor_id": str(row.access_key.actor_id),
                },
            )
        db.commit()
        db.refresh(row.access_key)
        clear_access_key_hotpath_cache(db, row.access_key.key_id)
        log.info(
            "access_key_revoke",
            access_key_id=str(row.access_key.id),
            key_id=row.access_key.key_id,
            actor_id=str(row.access_key.actor_id),
        )

    return row


def delete_access_key(
    db: Session, key_id: str, *, event_context: EventContext | None = None
) -> None:
    row = get_access_key_by_key_id(db, key_id)
    metadata = {
        "access_key_id": str(row.access_key.id),
        "key_id": row.access_key.key_id,
        "actor_id": str(row.access_key.actor_id),
    }
    db.delete(row.access_key)
    if event_context is not None:
        create_audit_event(
            db,
            operation="access_key.deleted",
            actor_id=event_context.actor_id,
            request_id=event_context.request_id,
            metadata=metadata,
        )
    db.commit()
    clear_access_key_hotpath_cache(db, key_id)
    log.info(
        "access_key_delete",
        access_key_id=str(row.access_key.id),
        key_id=row.access_key.key_id,
        actor_id=str(row.access_key.actor_id),
    )


def generate_key_id() -> str:
    return f"RK{secrets.token_hex(16).upper()}"


def generate_secret_access_key() -> str:
    return secrets.token_urlsafe(32)
