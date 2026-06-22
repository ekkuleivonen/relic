import uuid
from typing import Protocol

from infra.db.stores.access_keys import AccessKeyRow
from infra.db.models import AccessKey


class AccessKeyStore(Protocol):
    def get_by_key_id(self, key_id: str) -> AccessKeyRow: ...

    def add(self, access_key: AccessKey) -> None: ...

    def revoke(self, access_key: AccessKey) -> None: ...

    def delete(self, access_key: AccessKey) -> None: ...
