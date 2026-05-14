from pathlib import Path

import settings as S
from alembic import command
from alembic.config import Config
from database import get_sessionmaker
from enums import UserRole
from models import Folder, User
from processors.registry import get_processor_kind, init_builtin_processors
from services import processors as processor_service
from sqlalchemy import select
from utils.logging import get_logger
from utils.passwords import hash_password

init_builtin_processors()

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


# Seeded out-of-the-box processors. Operators can disable or remove them
# from the admin UI; ``upsert_seed_processor`` only creates them on first run.
SEEDED_PROCESSOR_KINDS: tuple[str, ...] = (
    "file_info",
    "image_meta",
    "html_meta",
    "pdf_meta",
    "parquet_meta",
    "csv_meta",
    "json_meta",
    "audio_meta",
    "video_meta",
    "office_doc_meta",
    "archive_meta",
    "text_meta",
)


def upsert_seeded_processors(db) -> None:
    for kind in SEEDED_PROCESSOR_KINDS:
        processor_kind = get_processor_kind(kind)
        processor_service.upsert_seed_processor(
            db,
            name=processor_kind.kind,
            kind=processor_kind.kind,
            subscribed_event_types=list(processor_kind.default_subscribed_event_types),
            mimetype_prefixes=list(processor_kind.default_mimetype_prefixes),
            extensions=list(processor_kind.default_extensions),
            config={},
        )


def seed() -> None:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        upsert_root_folder(db)
        upsert_admin_user(db)
        db.commit()
        upsert_seeded_processors(db)
        db.commit()


def main():
    run_migrations()
    seed()


if __name__ == "__main__":
    main()
