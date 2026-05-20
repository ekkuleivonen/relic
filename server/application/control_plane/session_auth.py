"""Session cookie authentication (control plane)."""

from application.uow import UnitOfWork
from infra.db.stores import auth
from ports.entities import User


def get_session_user(uow: UnitOfWork, token: str | None) -> User | None:
    return auth.get_session_user(uow.session, token)
