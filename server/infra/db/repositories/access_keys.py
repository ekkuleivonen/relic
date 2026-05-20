from application.control_plane.access_keys import AccessKeyRow
from domain.exceptions import ResourceNotFound
from infra.db.models import AccessKey, User
from ports.repositories.access_keys import AccessKeyStore
from sqlalchemy import select
from sqlalchemy.orm import Session


class SqlAlchemyAccessKeyStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_key_id(self, key_id: str) -> AccessKeyRow:
        row = self._session.execute(
            select(AccessKey, User)
            .join(User, User.id == AccessKey.actor_id)
            .where(AccessKey.key_id == key_id)
        ).first()
        if row is None:
            raise ResourceNotFound("Access key not found")
        return AccessKeyRow(access_key=row.AccessKey, user=row.User)

    def add(self, access_key: AccessKey) -> None:
        self._session.add(access_key)
        self._session.flush()

    def revoke(self, access_key: AccessKey) -> None:
        if access_key.revoked_at is not None:
            return
        import datetime as dt

        access_key.revoked_at = dt.datetime.now(dt.UTC)
        self._session.flush()

    def delete(self, access_key: AccessKey) -> None:
        self._session.delete(access_key)


def build_access_key_store(session: Session) -> AccessKeyStore:
    return SqlAlchemyAccessKeyStore(session)
