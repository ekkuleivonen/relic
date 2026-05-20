from typing import Protocol

from infra.db.models import BucketProbe
from sqlalchemy.orm import Session


class CachePort(Protocol):
    def invalidate_list_objects(self) -> None: ...

    def invalidate_folder_hotpath(self, session: Session) -> None: ...

    def invalidate_access_key(self, session: Session, key_id: str | None = None) -> None: ...
