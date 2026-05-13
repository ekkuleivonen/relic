from sqlalchemy import select

import settings as S
from database import get_sessionmaker
from models import Folder, User
from processors.meta_extract import (
    DEFAULT_SUBSCRIBED_EVENT_TYPES as META_EXTRACT_DEFAULT_TYPES,
    KIND as META_EXTRACT_KIND,
)
from processors.registry import init_builtin_substrates
from schema_plan import BucketTier, UserRole
from services import processors as processor_service
from utils.passwords import hash_password

init_builtin_substrates()


def upsert_root_folder(db) -> Folder:
    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    if root:
        return root

    root = Folder(
        name="",
        parent_id=None,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db.add(root)
    return root


def upsert_admin_user(db) -> User:
    email = S.RELIC_ADMIN_EMAIL
    admin = db.scalar(select(User).where(User.email == email))
    if admin:
        return admin

    admin = User(
        name=S.RELIC_ADMIN_NAME,
        email=email,
        password_hash=hash_password(S.RELIC_ADMIN_PASSWORD),
        role=UserRole.ADMIN,
    )
    db.add(admin)
    return admin


def upsert_meta_extract_processor(db) -> None:
    processor_service.upsert_seed_processor(
        db,
        name=META_EXTRACT_KIND,
        kind=META_EXTRACT_KIND,
        subscribed_event_types=list(META_EXTRACT_DEFAULT_TYPES),
        config={},
    )


def seed() -> None:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        upsert_root_folder(db)
        upsert_admin_user(db)
        db.commit()
        upsert_meta_extract_processor(db)
        db.commit()


def main():
    seed()


if __name__ == "__main__":
    main()
