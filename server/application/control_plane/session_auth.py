"""Control-plane authentication (session cookie or access key Bearer token)."""

from application.control_plane import access_key_auth
from application.uow import UnitOfWork
from infra.db.stores import auth
from ports.entities import User


def get_authenticated_user(
    uow: UnitOfWork,
    *,
    session_token: str | None,
    authorization: str | None,
) -> User | None:
    user = auth.get_session_user(uow.session, session_token)
    if user is not None:
        return user

    return access_key_auth.authenticate_bearer_token(uow, authorization)
