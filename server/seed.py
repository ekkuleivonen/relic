from sqlalchemy import select

import settings as S
from database import get_sessionmaker
from models import Folder, User
from schema_plan import ROOT_FOLDER_SCHEMA, BucketTier, UserRole
from utils.passwords import hash_password


def upsert_root_folder(db) -> Folder:
    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    if root:
        return root

    root = Folder(
        name="",
        parent_id=None,
        schema=ROOT_FOLDER_SCHEMA,
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


def seed() -> None:
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        upsert_root_folder(db)
        upsert_admin_user(db)
        db.commit()


def main():
    seed()


if __name__ == "__main__":
    main()
