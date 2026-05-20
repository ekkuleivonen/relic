"""Access key Bearer authentication for the JSON control plane."""

import secrets

from application.uow import UnitOfWork
from domain.auth.bearer import parse_bearer_access_key
from domain.exceptions import ResourceNotFound
from infra.db.stores import access_keys
from ports.entities import User
from utils.logging import get_logger

log = get_logger(__name__)


def is_bearer_authorization(authorization: str | None) -> bool:
    if not authorization:
        return False
    scheme, _, _token = authorization.partition(" ")
    return scheme.lower() == "bearer"


def authenticate_bearer_token(
    uow: UnitOfWork, authorization: str | None
) -> User | None:
    user, _failure_reason = resolve_bearer_authentication(uow, authorization)
    return user


def resolve_bearer_authentication(
    uow: UnitOfWork, authorization: str | None
) -> tuple[User | None, str | None]:
    parsed = parse_bearer_access_key(authorization)
    if parsed is None:
        if is_bearer_authorization(authorization):
            return None, "malformed"
        return None, None

    key_id, secret = parsed
    try:
        row = access_keys.get_access_key_by_key_id(uow.session, key_id)
    except ResourceNotFound:
        return None, "unknown_key"

    if row.access_key.revoked_at is not None:
        return None, "revoked"

    if not secrets.compare_digest(row.access_key.secret_access_key, secret):
        return None, "invalid_secret"

    access_keys.mark_access_key_used(uow.session, row.access_key)
    return row.user, None


def record_bearer_auth_failure(
    uow: UnitOfWork,
    *,
    authorization: str | None,
    request_id: str | None,
    reason: str,
) -> None:
    parsed = parse_bearer_access_key(authorization)
    metadata: dict[str, str | None] = {"reason": reason}
    if parsed is not None:
        metadata["key_id"] = parsed[0]

    uow.audit.emit(
        operation="auth.bearer.failed",
        status="failed",
        request_id=request_id,
        metadata=metadata,
    )
    log.info("auth_bearer_failed", reason=reason, key_id=metadata.get("key_id"))
