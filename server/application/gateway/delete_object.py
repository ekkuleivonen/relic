"""S3 DeleteObject — shared with control-plane file delete."""

from application.context import Actor
from application.control_plane.remove_file import remove_file_record
from infra.gateway.object_paths import resolve_existing_object_path
from infra.gateway.object_types import DeleteObjectResult
from application.uow import UnitOfWork
from enums import Permission
from ports.entities import User


def delete_object(
    uow: UnitOfWork,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> DeleteObjectResult:
    folder, file_name = resolve_existing_object_path(
        uow.session, bucket_name=bucket_name, key=key
    )
    if folder is None:
        return DeleteObjectResult(existed=False)

    if current_user is not None:
        uow.permissions.require_folder_permission(
            Actor.from_user(current_user), folder.id, Permission.DELETE
        )

    file = uow.files.get_by_folder_and_name(folder.id, file_name)
    if file is None:
        return DeleteObjectResult(existed=False)

    remove_file_record(uow, file=file)
    return DeleteObjectResult(existed=True)
