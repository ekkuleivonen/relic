import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

T = TypeVar("T")

_REQUEST_CACHE_KEY = "s3_hotpath_cache"


@dataclass(frozen=True)
class TtlCacheEntry:
    expires_at: float
    value: Any


_LIST_OBJECTS_RESPONSE_CACHE: dict[Any, TtlCacheEntry] = {}


def begin_request(db: Session) -> None:
    db.info[_REQUEST_CACHE_KEY] = {}


def request_cache(db: Session) -> dict[str, Any]:
    cache = db.info.get(_REQUEST_CACHE_KEY)
    if cache is None:
        cache = {}
        db.info[_REQUEST_CACHE_KEY] = cache
    return cache


def get_or_set_request(db: Session, key: str, factory: Callable[[], T]) -> T:
    cache = request_cache(db)
    if key not in cache:
        cache[key] = factory()
    return cache[key]


def engine_cache_key(db: Session) -> int:
    bind = db.get_bind()
    if isinstance(bind, Engine):
        return id(bind)
    return id(bind.engine)


def monotonic_now() -> float:
    return time.monotonic()


def get_ttl(
    cache: dict[Any, TtlCacheEntry],
    key: Any,
    *,
    now: float | None = None,
) -> Any | None:
    current = monotonic_now() if now is None else now
    entry = cache.get(key)
    if entry is None:
        return None
    if entry.expires_at <= current:
        cache.pop(key, None)
        return None
    return entry.value


def set_ttl(
    cache: dict[Any, TtlCacheEntry],
    key: Any,
    value: T,
    *,
    ttl_seconds: int,
    now: float | None = None,
) -> T:
    current = monotonic_now() if now is None else now
    cache[key] = TtlCacheEntry(expires_at=current + ttl_seconds, value=value)
    return value


def pop_ttl(cache: dict[Any, TtlCacheEntry], key: Any) -> None:
    cache.pop(key, None)


def clear_request(db: Session) -> None:
    db.info.pop(_REQUEST_CACHE_KEY, None)


def uuid_key(value: uuid.UUID) -> str:
    return str(value)


def get_list_objects_response(key: Any) -> str | None:
    return get_ttl(_LIST_OBJECTS_RESPONSE_CACHE, key)


def set_list_objects_response(
    key: Any,
    value: str,
    *,
    ttl_seconds: int,
) -> str:
    return set_ttl(
        _LIST_OBJECTS_RESPONSE_CACHE,
        key,
        value,
        ttl_seconds=ttl_seconds,
    )


def clear_list_objects_response_cache() -> None:
    _LIST_OBJECTS_RESPONSE_CACHE.clear()
