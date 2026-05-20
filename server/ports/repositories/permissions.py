import uuid
from typing import Protocol

from application.context import Actor
from enums import Permission
from infra.db.models import File, Folder


class PermissionStore(Protocol):
    def get_file_for_actor(
        self, actor: Actor, file_id: uuid.UUID, permission: Permission
    ) -> File: ...

    def require_folder(self, folder_id: uuid.UUID) -> Folder: ...

    def require_folder_permission(
        self, actor: Actor, folder_id: uuid.UUID, permission: Permission
    ) -> None: ...

    def get_user(self, actor: Actor): ...

    def resolve_folder_path(self, folder: Folder) -> str: ...

    def effective_permissions(self, actor: Actor, folder_id: uuid.UUID) -> int: ...
