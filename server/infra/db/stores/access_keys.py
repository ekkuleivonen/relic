import datetime as dt
import json
import secrets
import uuid
from dataclasses import dataclass

import settings as S
from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.exceptions import ResourceNotFound
from infra.cache.codec import access_key_cache_key
from infra.cache.hotpath import TtlCacheEntry, get_ttl, monotonic_now, set_ttl
from infra.cache.scope import deployment_scope
from infra.cache.tiered import get_tiered_cache
from infra.db.models import AccessKey, User
from utils.logging import get_logger

log = get_logger(__name__)

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


def _encode_access_key_credentials(
    credentials: ActiveAccessKeyCredentials,
) -> bytes:
    payload = {
        "access_key_id": str(credentials.access_key_id),
        "user_id": str(credentials.user_id),
        "secret_access_key": credentials.secret_access_key,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _decode_access_key_credentials(value: bytes) -> ActiveAccessKeyCredentials:
    payload = json.loads(value.decode("utf-8"))
    return ActiveAccessKeyCredentials(
        access_key_id=uuid.UUID(payload["access_key_id"]),
        user_id=uuid.UUID(payload["user_id"]),
        secret_access_key=payload["secret_access_key"],
    )


def list_access_keys(db: Session) -> list[AccessKeyRow]:
    rows = db.execute(
        select(AccessKey, User)
        .join(User, User.id == AccessKey.actor_id)
        .order_by(User.email, AccessKey.created_at.desc())
    ).all()
    return [AccessKeyRow(access_key=row.AccessKey, user=row.User) for row in rows]


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
    scope = deployment_scope()
    cache = get_tiered_cache("access_key_active")
    cache_key = access_key_cache_key(scope, key_id)
    cached = cache.get(cache_key)
    if cached is not None:
        return _decode_access_key_credentials(cached)

    row = get_active_access_key_by_key_id(db, key_id)
    credentials = ActiveAccessKeyCredentials(
        access_key_id=row.access_key.id,
        user_id=row.user.id,
        secret_access_key=row.access_key.secret_access_key,
    )
    cache.set(
        cache_key,
        _encode_access_key_credentials(credentials),
        ttl_seconds=S.S3_ACCESS_KEY_CACHE_TTL_SECONDS,
    )
    return credentials


def authenticate_access_key(db: Session, *, key_id: str, secret: str) -> User | None:
    try:
        row = get_active_access_key_by_key_id(db, key_id)
    except ResourceNotFound:
        return None

    if not secrets.compare_digest(row.access_key.secret_access_key, secret):
        return None

    mark_access_key_used(db, row.access_key)
    return row.user


def mark_access_key_used(db: Session, access_key: AccessKey) -> None:
    mark_access_key_used_by_id(db, access_key.id)


def mark_access_key_used_by_id(db: Session, access_key_id: uuid.UUID) -> None:
    cache_key = (id(db.get_bind()), access_key_id)
    if get_ttl(_LAST_USED_WRITE_CACHE, cache_key) is not None:
        return

    access_key = db.get(AccessKey, access_key_id)
    if access_key is None:
        return

    access_key.last_used_at = dt.datetime.now(dt.UTC)
    set_ttl(
        _LAST_USED_WRITE_CACHE,
        cache_key,
        True,
        ttl_seconds=S.S3_ACCESS_KEY_LAST_USED_DEBOUNCE_SECONDS,
        now=monotonic_now(),
    )


def clear_access_key_hotpath_cache(db: Session, key_id: str | None = None) -> None:
    cache = get_tiered_cache("access_key_active")
    scope = deployment_scope()
    if key_id is None:
        cache.invalidate()
        return
    cache.invalidate_key(access_key_cache_key(scope, key_id))


def generate_key_id() -> str:
    return f"RK{secrets.token_hex(16).upper()}"


def generate_secret_access_key() -> str:
    return secrets.token_urlsafe(32)
