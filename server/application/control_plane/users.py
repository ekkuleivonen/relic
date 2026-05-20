import uuid

from application.uow import UnitOfWork
from infra.db.models import User


def list_users(uow: UnitOfWork) -> list[User]:
    return uow.users.list_all()


def get_user(uow: UnitOfWork, user_id: uuid.UUID) -> User:
    return uow.users.get(user_id)
