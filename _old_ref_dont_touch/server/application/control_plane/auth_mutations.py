import uuid

from application.context import EventContext
from infra.db.stores import auth
from application.uow import UnitOfWork
from domain.exceptions import BadRequestError
from infra import metrics
from ports.entities import User


def login(
    uow: UnitOfWork,
    *,
    email: str,
    password: str,
    event_context: EventContext | None = None,
) -> User:
    try:
        user = auth.authenticate_user(uow.session, email=email, password=password)
    except BadRequestError:
        metrics.observe_auth_attempt(auth_type="session", result="failed")
        uow.audit.emit(
            operation="auth.login.failed",
            status="failed",
            request_id=event_context.request_id if event_context else None,
            metadata={"email": email},
        )
        raise
    metrics.observe_auth_attempt(auth_type="session", result="success")
    uow.audit.record(
        operation="auth.login.succeeded",
        event_context=event_context,
        metadata={"email": user.email},
    )
    return user


def logout(
    uow: UnitOfWork,
    *,
    user: User | None,
    event_context: EventContext | None = None,
) -> None:
    uow.audit.emit(
        operation="auth.logout",
        actor_id=user.id if user else None,
        request_id=event_context.request_id if event_context else None,
        metadata={"email": user.email} if user else {},
    )
