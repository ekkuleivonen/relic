import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from models import Base, Blob, File, Folder, FolderAccess, PARSE_STATUS_COMPLETED
from schema_plan import ROOT_FOLDER_SCHEMA, BucketTier, Permission
from services.auth import create_session_token
from tests.factories.models import BucketFactory, UserFactory


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
def user(db_session):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def client(db_session, user):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
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


@pytest.fixture()
def photos_folder(db_session, root_folder):
    folder = Folder(
        name="photos",
        parent_id=root_folder.id,
        schema=ROOT_FOLDER_SCHEMA,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def archives_folder(db_session, root_folder):
    folder = Folder(
        name="archives",
        parent_id=root_folder.id,
        schema=ROOT_FOLDER_SCHEMA,
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def physical_bucket(db_session):
    bucket = BucketFactory.build(name="hot")
    bucket.probe_latency_put_ms = 10
    bucket.probe_latency_head_ms = 10
    bucket.probe_latency_get_ms = 10
    bucket.probe_latency_delete_ms = 10
    db_session.add(bucket)
    db_session.commit()
    return bucket


def grant(db_session, user, folder, permissions: int) -> FolderAccess:
    access = FolderAccess(
        user_id=user.id, folder_id=folder.id, permissions=permissions
    )
    db_session.add(access)
    db_session.commit()
    return access


def make_file(db_session, *, folder, blob, name, user, parser_meta=None):
    parser_meta = parser_meta or {
        "file": {
            "original_filename": name,
            "size": 9,
            "mime_type": "image/jpeg",
            "extension": "jpg",
        }
    }
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        uploaded_by=user.id,
        name=name,
        parse_status=PARSE_STATUS_COMPLETED,
        ingest_meta={"original_filename": name},
        parser_meta=parser_meta,
    )
    db_session.add(file)
    db_session.commit()
    return file


def make_blob(db_session, *, bucket, content_hash):
    blob = Blob(
        bucket_id=bucket.id,
        bucket_key="2026/05/09/blob",
        content_hash=content_hash,
        size_bytes=9,
        refcount=1,
    )
    db_session.add(blob)
    db_session.commit()
    return blob


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------


def test_move_file_changes_folder_id(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(db_session, bucket=physical_bucket, content_hash=(1).to_bytes(32, "big"))
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg")

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["folder_id"] == str(archives_folder.id)

    db_session.refresh(file)
    assert file.folder_id == archives_folder.id
    db_session.refresh(blob)
    assert blob.refcount == 1


def test_move_file_defers_parser_schema_validation(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    archives_folder.schema = {
        **ROOT_FOLDER_SCHEMA,
        "required": [*ROOT_FOLDER_SCHEMA.get("required", []), "checked"],
        "properties": {
            **ROOT_FOLDER_SCHEMA["properties"],
            "checked": {"type": "boolean"},
        },
    }
    db_session.commit()
    blob = make_blob(db_session, bucket=physical_bucket, content_hash=(2).to_bytes(32, "big"))
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg")

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 200


def test_move_requires_delete_on_source(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(db_session, bucket=physical_bucket, content_hash=(3).to_bytes(32, "big"))
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg")

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 403


def test_move_requires_write_on_destination(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ))
    blob = make_blob(db_session, bucket=physical_bucket, content_hash=(4).to_bytes(32, "big"))
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg")

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 403


def test_move_conflicts_when_name_taken_in_destination(
    client, db_session, user, photos_folder, archives_folder, physical_bucket
):
    grant(
        db_session,
        user,
        photos_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    grant(db_session, user, archives_folder, int(Permission.READ | Permission.WRITE))
    blob_a = make_blob(db_session, bucket=physical_bucket, content_hash=(5).to_bytes(32, "big"))
    blob_b = make_blob(db_session, bucket=physical_bucket, content_hash=(6).to_bytes(32, "big"))
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob_a, name="cat.jpg")
    make_file(db_session, user=user, folder=archives_folder, blob=blob_b, name="cat.jpg")

    response = client.post(
        f"/api/files/{file.id}/move",
        json={"destination_folder_id": str(archives_folder.id)},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_rename_file_in_place(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    blob = make_blob(db_session, bucket=physical_bucket, content_hash=(7).to_bytes(32, "big"))
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg")

    response = client.patch(
        f"/api/files/{file.id}",
        json={"name": "feline.jpg"},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(file)
    assert file.name == "feline.jpg"
    assert file.parse_status == 1
    assert file.parser_meta == {}


def test_rename_conflicts_with_existing_name(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ | Permission.WRITE))
    blob_a = make_blob(db_session, bucket=physical_bucket, content_hash=(8).to_bytes(32, "big"))
    blob_b = make_blob(db_session, bucket=physical_bucket, content_hash=(9).to_bytes(32, "big"))
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob_a, name="cat.jpg")
    make_file(db_session, user=user, folder=photos_folder, blob=blob_b, name="dog.jpg")

    response = client.patch(
        f"/api/files/{file.id}",
        json={"name": "dog.jpg"},
    )
    assert response.status_code == 409


def test_rename_requires_write(
    client, db_session, user, photos_folder, physical_bucket
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob = make_blob(
        db_session, bucket=physical_bucket, content_hash=(10).to_bytes(32, "big")
    )
    file = make_file(db_session, user=user, folder=photos_folder, blob=blob, name="cat.jpg")

    response = client.patch(
        f"/api/files/{file.id}",
        json={"name": "feline.jpg"},
    )
    assert response.status_code == 403
