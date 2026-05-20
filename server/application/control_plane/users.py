import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from domain.exceptions import ResourceNotFound
from infra.db.models import User


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.email)).all())


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ResourceNotFound("User not found")

    return user
