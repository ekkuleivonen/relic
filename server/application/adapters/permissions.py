import uuid

from application.context import Actor
from application.control_plane import file_access, folder_access
from domain.exceptions import ResourceNotFound
from enums import Permission
from infra.db.models import File, Folder, User
from ports.repositories.permissions import PermissionStore
from sqlalchemy.orm import Session


class SqlAlchemyPermissionStore:
    """Permission checks backed by folder-access rules and SQLAlchemy session I/O."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _user(self, actor: Actor) -> User:
        user = self._session.get(User, actor.id)
        if user is None:
            raise ResourceNotFound("User not found")
        return user

    def get_file_for_actor(
        self, actor: Actor, file_id: uuid.UUID, permission: Permission
    ) -> File:
        return file_access.get_file_for_actor(
            self._session, actor, file_id, permission
        )

    def require_folder(self, folder_id: uuid.UUID) -> Folder:
        return folder_access.require_folder(self._session, folder_id)

    def require_folder_permission(
        self, actor: Actor, folder_id: uuid.UUID, permission: Permission
    ) -> None:
        folder_access.require_folder_permission_strict(
            self._session, self._user(actor), folder_id, permission
        )

    def get_user(self, actor: Actor) -> User:
        return self._user(actor)

    def resolve_folder_path(self, folder: Folder) -> str:
        return folder_access.resolve_folder_path(self._session, folder)

    def effective_permissions(self, actor: Actor, folder_id: uuid.UUID) -> int:
        return folder_access.get_effective_permissions(
            self._session, self._user(actor), folder_id
        )


def build_permission_store(session: Session) -> PermissionStore:
    return SqlAlchemyPermissionStore(session)
