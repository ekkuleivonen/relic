import posixpath
from pathlib import PurePosixPath

from domain.exceptions import BadRequestError, ResourceNotFound
from enums import Permission
from infra.db.models import Folder, User
from infra.gateway.bucket import gateway_bucket_name, require_gateway_bucket
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.db.stores import folder_access
from infra.cache import folder_access as folder_access_cache


def normalize_key(key: str) -> str:
    normalized_key = posixpath.normpath(key)
    if normalized_key.startswith("../") or normalized_key == "..":
        raise BadRequestError("Object key cannot escape the bucket")
    return normalized_key


def key_parts(key: str) -> list[str]:
    normalized_key = normalize_key(key)
    return [
        part for part in PurePosixPath(normalized_key).parts if part not in ("", ".")
    ]


def require_root_folder(db: Session) -> Folder:
    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    if root is None:
        raise ResourceNotFound("Root folder not found")
    return root


def resolve_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User,
) -> tuple[Folder, str]:
    require_gateway_bucket(bucket_name)
    parts = key_parts(key)
    if not parts:
        raise BadRequestError("Object key must include a file name")

    parent = require_root_folder(db)
    for folder_name in parts[:-1]:
        parent = get_or_create_child_folder(
            db,
            parent=parent,
            name=folder_name,
            current_user=current_user,
        )
    return parent, parts[-1]


def get_or_create_child_folder(
    db: Session,
    *,
    parent: Folder,
    name: str,
    current_user: User,
) -> Folder:
    child = db.scalar(
        select(Folder).where(Folder.parent_id == parent.id, Folder.name == name)
    )
    if child:
        return child

    folder_access.require_folder_permission_strict(
        db,
        current_user,
        parent.id,
        Permission.WRITE,
    )

    child = Folder(
        parent_id=parent.id,
        name=name,
    )
    db.add(child)
    db.flush()
    folder_access_cache.clear_hotpath_cache(db)
    return child


def resolve_existing_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
) -> tuple[Folder | None, str]:
    require_gateway_bucket(bucket_name)
    parts = key_parts(key)
    if not parts:
        return None, ""

    parent = require_root_folder(db)
    for folder_name in parts[:-1]:
        child = db.scalar(
            select(Folder).where(
                Folder.parent_id == parent.id, Folder.name == folder_name
            )
        )
        if child is None:
            return None, ""
        parent = child

    return parent, parts[-1]


def require_existing_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
) -> tuple[Folder, str]:
    folder, file_name = resolve_existing_object_path(
        db, bucket_name=bucket_name, key=key
    )
    if folder is None:
        raise ResourceNotFound("Object not found")
    return folder, file_name


def build_object_key_for_folder_path(*, folder_path: str, filename: str) -> str:
    parts = [part for part in folder_path.split("/") if part]
    if not parts:
        raise BadRequestError("File is not under a folder")
    return "/".join([*parts, filename])


def build_bucket_and_key_for_file(db: Session, file) -> tuple[str, str]:
    """Compose (gateway_bucket, object_key) for a File."""
    folder_path = folder_access.resolve_folder_path(
        db, db.get(Folder, file.folder_id)
    )
    return gateway_bucket_name(), build_object_key_for_folder_path(
        folder_path=folder_path,
        filename=file.name,
    )


def build_bucket_and_key_for_destination(
    db: Session,
    *,
    folder: Folder,
    filename: str,
) -> tuple[str, str]:
    if "/" in filename:
        raise BadRequestError("Filename cannot contain '/'")
    folder_path = folder_access.resolve_folder_path(db, folder)
    parts = [part for part in folder_path.split("/") if part]
    if not parts:
        raise BadRequestError(
            "Files must be uploaded into a subfolder, not the root folder."
        )
    return gateway_bucket_name(), build_object_key_for_folder_path(
        folder_path=folder_path,
        filename=filename,
    )
