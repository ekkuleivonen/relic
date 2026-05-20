"""Access key Bearer authentication for the JSON control plane."""

from application.uow import UnitOfWork
from domain.auth.bearer import parse_bearer_access_key
from infra.db.stores import access_keys
from ports.entities import User


def authenticate_bearer_token(
    uow: UnitOfWork, authorization: str | None
) -> User | None:
    parsed = parse_bearer_access_key(authorization)
    if parsed is None:
        return None

    key_id, secret = parsed
    return access_keys.authenticate_access_key(
        uow.session, key_id=key_id, secret=secret
    )
