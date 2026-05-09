import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from models import Base, File, Folder, User
from schema_plan import ROOT_FOLDER_SCHEMA, BucketTier, UserRole
from services.auth import create_session_token
from tests.factories.models import BlobFactory, BucketFactory
from utils.passwords import hash_password


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


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    user = User(
        name="User",
        email="user@relic.local",
        password_hash=hash_password("password"),
        role=UserRole.USER,
    )
    db_session.add(user)
    db_session.commit()
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(user))
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def root_folder(db_session):
    root = Folder(
        name="",
        parent_id=None,
        schema=ROOT_FOLDER_SCHEMA,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(root)
    db_session.commit()
    return root


def add_folder(db_session, parent: Folder, name: str) -> Folder:
    folder = Folder(
        name=name,
        parent_id=parent.id,
        schema=ROOT_FOLDER_SCHEMA,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


def test_get_folder_tree_returns_nested_filesystem(client, db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    add_folder(db_session, photos, "raw")
    add_folder(db_session, root_folder, "docs")

    response = client.get("/folders/tree")

    assert response.status_code == 200
    tree = response.json()
    assert tree["name"] == ""
    assert [child["name"] for child in tree["children"]] == ["docs", "photos"]
    assert tree["children"][1]["children"][0]["name"] == "raw"


def test_list_files_filters_by_folder(client, db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    docs = add_folder(db_session, root_folder, "docs")
    bucket = BucketFactory.build()
    db_session.add(bucket)
    db_session.flush()
    blob = BlobFactory.build(bucket_id=bucket.id)
    db_session.add(blob)
    db_session.flush()
    db_session.add_all(
        [
            File(
                folder_id=photos.id,
                blob_id=blob.id,
                name="image.jpg",
                meta={
                    "original_name": "image.jpg",
                    "file_size": 1024,
                    "mime_type": "image/jpeg",
                    "extension": ".jpg",
                },
            ),
            File(
                folder_id=docs.id,
                blob_id=blob.id,
                name="notes.txt",
                meta={
                    "original_name": "notes.txt",
                    "file_size": 12,
                    "mime_type": "text/plain",
                    "extension": ".txt",
                },
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/files/?folder_id={photos.id}")

    assert response.status_code == 200
    files = response.json()
    assert [file["name"] for file in files] == ["image.jpg"]
    assert files[0]["meta"]["file_size"] == 1024
