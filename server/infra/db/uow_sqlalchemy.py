from application.uow import UnitOfWork
from infra.object_storage.registry import build_storage_registry
from infra.db.repositories.access_keys import build_access_key_store
from infra.db.repositories.audit import build_audit_port
from infra.cache.list_objects import build_cache_port
from infra.db.repositories.blobs import build_blob_store
from infra.db.repositories.buckets import build_bucket_store
from infra.db.repositories.files import build_file_store
from infra.db.repositories.folders import build_folder_store
from infra.db.repositories.multipart import build_multipart_store
from application.adapters.permissions import build_permission_store
from infra.db.repositories.search import build_search_store
from infra.db.repositories.users import build_user_store
from ports.audit import AuditPort
from ports.cache import CachePort
from ports.repositories.access_keys import AccessKeyStore
from ports.repositories.blobs import BlobStore
from ports.repositories.buckets import BucketStore
from ports.repositories.files import FileStore
from ports.repositories.folders import FolderStore
from ports.repositories.multipart import MultipartStore
from ports.repositories.permissions import PermissionStore
from ports.repositories.search import SearchStore
from ports.repositories.users import UserStore
from ports.storage_registry import StorageRegistry
from sqlalchemy.orm import Session


class SqlAlchemyUnitOfWork:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._files: FileStore | None = None
        self._folders: FolderStore | None = None
        self._buckets: BucketStore | None = None
        self._blobs: BlobStore | None = None
        self._users: UserStore | None = None
        self._access_keys: AccessKeyStore | None = None
        self._permissions: PermissionStore | None = None
        self._search: SearchStore | None = None
        self._multipart: MultipartStore | None = None
        self._cache: CachePort | None = None
        self._audit: AuditPort | None = None
        self._storage: StorageRegistry | None = None

    @property
    def session(self) -> Session:
        return self._session

    @property
    def files(self) -> FileStore:
        if self._files is None:
            self._files = build_file_store(self._session)
        return self._files

    @property
    def folders(self) -> FolderStore:
        if self._folders is None:
            self._folders = build_folder_store(self._session)
        return self._folders

    @property
    def buckets(self) -> BucketStore:
        if self._buckets is None:
            self._buckets = build_bucket_store(self._session)
        return self._buckets

    @property
    def blobs(self) -> BlobStore:
        if self._blobs is None:
            self._blobs = build_blob_store(self._session)
        return self._blobs

    @property
    def users(self) -> UserStore:
        if self._users is None:
            self._users = build_user_store(self._session)
        return self._users

    @property
    def access_keys(self) -> AccessKeyStore:
        if self._access_keys is None:
            self._access_keys = build_access_key_store(self._session)
        return self._access_keys

    @property
    def permissions(self) -> PermissionStore:
        if self._permissions is None:
            self._permissions = build_permission_store(self._session)
        return self._permissions

    @property
    def search(self) -> SearchStore:
        if self._search is None:
            self._search = build_search_store(self._session)
        return self._search

    @property
    def multipart(self) -> MultipartStore:
        if self._multipart is None:
            self._multipart = build_multipart_store(self._session)
        return self._multipart

    @property
    def cache(self) -> CachePort:
        if self._cache is None:
            self._cache = build_cache_port()
        return self._cache

    @property
    def audit(self) -> AuditPort:
        if self._audit is None:
            self._audit = build_audit_port(self._session)
        return self._audit

    @property
    def storage(self) -> StorageRegistry:
        if self._storage is None:
            self._storage = build_storage_registry()
        return self._storage

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def close(self) -> None:
        """Session lifecycle is owned by the caller (HTTP ``get_db`` or worker ``with sm()``)."""
        return


def build_uow(session: Session) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)
