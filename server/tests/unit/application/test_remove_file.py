import uuid
from dataclasses import dataclass, field

import pytest
from application.control_plane.remove_file import remove_file_by_id
from application.context import Actor
from domain.exceptions import PermissionDenied
from enums import Permission
from ports.entities import Blob, File


@dataclass
class FakeFileStore:
    deleted: list[File] = field(default_factory=list)

    def delete(self, file: File) -> None:
        self.deleted.append(file)

    def ensure_blob_loaded(self, file: File) -> File:
        return file


@dataclass
class FakePermissionStore:
    file: File
    deny: bool = False

    def get_file_for_actor(self, actor: Actor, file_id: uuid.UUID, permission: Permission) -> File:
        if self.deny:
            raise PermissionDenied("denied")
        if file_id != self.file.id:
            raise PermissionDenied("not found")
        return self.file


@dataclass
class FakeCache:
    list_objects_cleared: int = 0
    folder_cleared: int = 0

    def invalidate_list_objects(self) -> None:
        self.list_objects_cleared += 1

    def invalidate_folder_hotpath(self, session) -> None:
        del session
        self.folder_cleared += 1


@dataclass
class FakeUnitOfWork:
    files: FakeFileStore
    permissions: FakePermissionStore
    cache: FakeCache
    session: object = None


def test_remove_file_by_id_deletes_and_invalidates_cache():
    file_id = uuid.uuid4()
    blob = Blob(
        id=uuid.uuid4(),
        storage_backend_id=uuid.uuid4(),
        bucket_key="k",
        content_hash=b"\x00" * 32,
        size_bytes=1,
    )
    file = File(
        id=file_id,
        folder_id=uuid.uuid4(),
        blob_id=blob.id,
        actor_id=uuid.uuid4(),
        name="a.txt",
        meta={},
    )
    file.blob = blob
    files = FakeFileStore()
    uow = FakeUnitOfWork(
        files=files,
        permissions=FakePermissionStore(file=file),
        cache=FakeCache(),
    )

    remove_file_by_id(uow, actor=Actor(id=uuid.uuid4()), file_id=file_id)

    assert files.deleted == [file]
    assert uow.cache.list_objects_cleared == 1
    assert uow.cache.folder_cleared == 1


def test_remove_file_by_id_checks_permission():
    file = File(
        id=uuid.uuid4(),
        folder_id=uuid.uuid4(),
        blob_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        name="a.txt",
        meta={},
    )
    uow = FakeUnitOfWork(
        files=FakeFileStore(),
        permissions=FakePermissionStore(file=file, deny=True),
        cache=FakeCache(),
    )

    with pytest.raises(PermissionDenied):
        remove_file_by_id(uow, actor=Actor(id=uuid.uuid4()), file_id=file.id)
