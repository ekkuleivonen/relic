from ports.cache import CachePort
from infra.cache.hotpath import clear_list_objects_response_cache
from application.control_plane import folder_access_cache
from application.control_plane import access_keys
from sqlalchemy.orm import Session


class ListObjectsCachePort:
    def invalidate_list_objects(self) -> None:
        clear_list_objects_response_cache()

    def invalidate_folder_hotpath(self, session: Session) -> None:
        folder_access_cache.clear_hotpath_cache(session)

    def invalidate_access_key(self, session: Session, key_id: str | None = None) -> None:
        access_keys.clear_access_key_hotpath_cache(session, key_id)


def build_cache_port() -> CachePort:
    return ListObjectsCachePort()
