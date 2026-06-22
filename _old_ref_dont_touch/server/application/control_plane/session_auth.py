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
    request_id: str | None = None,
) -> tuple[User | None, bool]:
    user = auth.get_session_user(uow.session, session_token)
    if user is not None:
        return user, False

    bearer_user, failure_reason = access_key_auth.resolve_bearer_authentication(
        uow, authorization
    )
    if bearer_user is not None:
        return bearer_user, False

    if failure_reason is not None:
        access_key_auth.record_bearer_auth_failure(
            uow,
            authorization=authorization,
            request_id=request_id,
            reason=failure_reason,
        )
        return None, True

    return None, False
