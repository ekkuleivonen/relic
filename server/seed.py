from pathlib import Path

import settings as S
from alembic import command
from alembic.config import Config
from constants import (
    META_EXTRACT_DEFAULT_SUBSCRIBED_EVENT_TYPES,
    META_EXTRACT_PROCESSOR_KIND,
)
from database import get_sessionmaker
from enums import BucketTier, UserRole
from models import Folder, User
from processors.registry import init_builtin_substrates
from services import processors as processor_service
from sqlalchemy import select
from utils.logging import get_logger
from utils.passwords import hash_password

init_builtin_substrates()

log = get_logger(__name__)
SERVER_DIR = Path(__file__).resolve().parent


def run_migrations() -> None:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "alembic"))

    log.info("running_database_migrations")
    command.upgrade(config, "head")
    log.info("database_migrations_complete")


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
        name=META_EXTRACT_PROCESSOR_KIND,
        kind=META_EXTRACT_PROCESSOR_KIND,
        subscribed_event_types=list(META_EXTRACT_DEFAULT_SUBSCRIBED_EVENT_TYPES),
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
    run_migrations()
    seed()


if __name__ == "__main__":
    main()
