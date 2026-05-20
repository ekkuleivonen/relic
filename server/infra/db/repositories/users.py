import uuid

from domain.exceptions import ConflictError, ResourceNotFound
from infra.db.models import File, User
from ports.repositories.users import UserStore
from sqlalchemy import select
from sqlalchemy.orm import Session


class SqlAlchemyUserStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: uuid.UUID) -> User:
        user = self._session.get(User, user_id)
        if user is None:
            raise ResourceNotFound("User not found")
        return user

    def ensure_email_available(
        self, email: str, *, excluding_user_id: uuid.UUID | None = None
    ) -> None:
        existing = self._session.scalar(select(User).where(User.email == email))
        if existing is not None and existing.id != excluding_user_id:
            raise ConflictError("User email already exists")

    def add(self, user: User) -> None:
        self._session.add(user)
        self._session.flush()

    def save(self, user: User) -> None:
        self._session.flush()
        self._session.refresh(user)

    def delete(self, user: User) -> None:
        self._session.delete(user)

    def has_uploaded_files(self, user_id: uuid.UUID) -> bool:
        uploaded_file_id = self._session.scalar(
            select(File.id).where(File.actor_id == user_id).limit(1)
        )
        return uploaded_file_id is not None


def build_user_store(session: Session) -> UserStore:
    return SqlAlchemyUserStore(session)
