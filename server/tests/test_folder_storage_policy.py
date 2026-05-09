from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from models import Base, Folder
from schema_plan import BucketTier
from services.folder_storage_policy import effective_cooldown_days, effective_min_tier


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        yield session


def test_effective_min_tier_inherits_from_ancestor(db_session):
    root = Folder(name="", parent_id=None, min_tier=int(BucketTier.WARM), cooldown_days=None)
    db_session.add(root)
    db_session.flush()
    mid = Folder(
        name="a",
        parent_id=root.id,
        min_tier=None,
        cooldown_days=None,
    )
    db_session.add(mid)
    db_session.flush()
    leaf = Folder(name="b", parent_id=mid.id, min_tier=None, cooldown_days=None)
    db_session.add(leaf)
    db_session.commit()

    assert effective_min_tier(db_session, leaf) == int(BucketTier.WARM)


def test_effective_min_tier_child_overrides(db_session):
    root = Folder(name="", parent_id=None, min_tier=int(BucketTier.HOT), cooldown_days=None)
    db_session.add(root)
    db_session.flush()
    leaf = Folder(
        name="a",
        parent_id=root.id,
        min_tier=int(BucketTier.COLD),
        cooldown_days=None,
    )
    db_session.add(leaf)
    db_session.commit()

    assert effective_min_tier(db_session, leaf) == int(BucketTier.COLD)


def test_effective_cooldown_days_inherits(db_session):
    root = Folder(
        name="",
        parent_id=None,
        min_tier=int(BucketTier.HOT),
        cooldown_days=90,
    )
    db_session.add(root)
    db_session.flush()
    leaf = Folder(
        name="a",
        parent_id=root.id,
        min_tier=int(BucketTier.HOT),
        cooldown_days=None,
    )
    db_session.add(leaf)
    db_session.commit()

    assert effective_cooldown_days(db_session, leaf) == 90
