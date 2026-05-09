import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from database import get_db
from file_meta import build_file_meta
from models import Base, File, Folder, FolderAccess, PARSE_STATUS_COMPLETED, User
from schema_plan import BucketTier, Permission, UserRole
from services.auth import create_session_token
from tests.factories.models import BlobFactory, BucketFactory, UserFactory
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
def user(db_session):
    user = User(
        name="User",
        email="user@relic.local",
        password_hash=hash_password("password"),
        role=UserRole.USER,
    )
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
        cooldown_days=None,
        min_tier=BucketTier.HOT,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


def grant_access(db_session, user: User, folder: Folder, permissions: int) -> None:
    db_session.add(
        FolderAccess(
            user_id=user.id,
            folder_id=folder.id,
            permissions=permissions,
        )
    )
    db_session.commit()


def test_get_folder_tree_returns_nested_filesystem(client, db_session, user, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    add_folder(db_session, photos, "raw")
    add_folder(db_session, root_folder, "docs")
    grant_access(db_session, user, root_folder, int(Permission.READ))

    response = client.get("/api/folders/tree")

    assert response.status_code == 200
    tree = response.json()
    assert tree["name"] == ""
    assert tree["path"] == "/"
    assert tree["effective_permissions"] == int(Permission.READ)
    assert [child["name"] for child in tree["children"]] == ["docs", "photos"]
    assert tree["children"][1]["children"][0]["name"] == "raw"
    assert tree["children"][1]["children"][0]["path"] == "/photos/raw"
    assert tree["children"][1]["children"][0]["effective_permissions"] == int(
        Permission.READ
    )


def test_get_folder_tree_omits_storage_policy_for_non_admin(
    client, db_session, user, root_folder
):
    photos = add_folder(db_session, root_folder, "photos")
    photos.cooldown_days = 7
    photos.min_tier = 2
    db_session.commit()

    grant_access(db_session, user, root_folder, int(Permission.READ))

    response = client.get("/api/folders/tree")

    assert response.status_code == 200
    tree = response.json()
    photos_node = next(c for c in tree["children"] if c["name"] == "photos")
    assert photos_node.get("min_tier") is None
    assert photos_node.get("cooldown_days") is None


def test_get_folder_tree_includes_storage_policy_for_admin(db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    photos.cooldown_days = 14
    photos.min_tier = 3
    db_session.commit()

    admin = UserFactory.build(email="admin-pol@relic.local", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as admin_client:
            admin_client.cookies.set("relic_session", create_session_token(admin))
            response = admin_client.get("/api/folders/tree")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    tree = response.json()
    node = next(c for c in tree["children"] if c["name"] == "photos")
    assert node["min_tier"] == 3
    assert node["cooldown_days"] == 14
    assert node["effective_min_tier"] == 3
    assert node["effective_cooldown_days"] == 14


def test_admin_get_folder_tree_bypasses_folder_access(db_session, root_folder):
    def override_get_db():
        yield db_session

    photos = add_folder(db_session, root_folder, "photos")
    add_folder(db_session, photos, "raw")
    admin = UserFactory.build(email="admin@relic.local", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.commit()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as admin_client:
            admin_client.cookies.set("relic_session", create_session_token(admin))
            response = admin_client.get("/api/folders/tree")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    tree = response.json()
    assert [child["name"] for child in tree["children"]] == ["photos"]
    assert tree["children"][0]["children"][0]["name"] == "raw"
    assert tree["children"][0]["children"][0]["path"] == "/photos/raw"
    assert tree["effective_permissions"] == int(
        Permission.READ | Permission.WRITE | Permission.DELETE | Permission.ENRICH
    )


def test_get_folder_tree_filters_to_readable_scopes(client, db_session, user, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    add_folder(db_session, photos, "raw")
    add_folder(db_session, root_folder, "docs")
    grant_access(db_session, user, photos, int(Permission.READ | Permission.WRITE))

    response = client.get("/api/folders/tree")

    assert response.status_code == 200
    tree = response.json()
    assert tree["name"] == ""
    assert tree["effective_permissions"] == 0
    assert [child["name"] for child in tree["children"]] == ["photos"]
    assert tree["children"][0]["effective_permissions"] == int(
        Permission.READ | Permission.WRITE
    )
    assert tree["children"][0]["children"][0]["name"] == "raw"


def test_get_folder_tree_reparents_readable_descendant_when_parent_is_unreadable(
    client, db_session, user, root_folder
):
    photos = add_folder(db_session, root_folder, "photos")
    e2e = add_folder(db_session, photos, "e2e")
    grant_access(db_session, user, e2e, int(Permission.READ))

    response = client.get("/api/folders/tree")

    assert response.status_code == 200
    tree = response.json()
    assert [child["name"] for child in tree["children"]] == ["e2e"]
    assert tree["children"][0]["path"] == "/photos/e2e"
    assert tree["children"][0]["parent_id"] == str(photos.id)


def test_get_folder_tree_returns_root_shell_without_grants(client, db_session, root_folder):
    add_folder(db_session, root_folder, "photos")

    response = client.get("/api/folders/tree")

    assert response.status_code == 200
    tree = response.json()
    assert tree["name"] == ""
    assert tree["effective_permissions"] == 0
    assert tree["children"] == []


def test_list_files_filters_by_folder(client, db_session, user, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    docs = add_folder(db_session, root_folder, "docs")
    grant_access(db_session, user, photos, int(Permission.READ))
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
                uploaded_by=user.id,
                name="image.jpg",
                parse_status=PARSE_STATUS_COMPLETED,
                meta=build_file_meta(
                    file_name="image.jpg",
                    size=1024,
                    user_meta={},
                    mimetype="image/jpeg",
                ),
            ),
            File(
                folder_id=docs.id,
                blob_id=blob.id,
                uploaded_by=user.id,
                name="notes.txt",
                parse_status=PARSE_STATUS_COMPLETED,
                meta=build_file_meta(
                    file_name="notes.txt",
                    size=12,
                    user_meta={},
                    mimetype="text/plain",
                ),
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/files/?folder_id={photos.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert [item["name"] for item in body["items"]] == ["image.jpg"]
    assert body["items"][0]["meta"]["size"] == 1024
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_list_files_rejects_unreadable_folder(client, db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")

    response = client.get(f"/api/files/?folder_id={photos.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Folder not found"


def test_recursive_list_files_excludes_unreadable_descendants(
    client, db_session, user, root_folder
):
    photos = add_folder(db_session, root_folder, "photos")
    raw = add_folder(db_session, photos, "raw")
    docs = add_folder(db_session, root_folder, "docs")
    grant_access(db_session, user, photos, int(Permission.READ))
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
                uploaded_by=user.id,
                name="image.jpg",
                parse_status=PARSE_STATUS_COMPLETED,
                meta=build_file_meta(file_name="image.jpg", size=1024, user_meta={}),
            ),
            File(
                folder_id=raw.id,
                blob_id=blob.id,
                uploaded_by=user.id,
                name="raw.nef",
                parse_status=PARSE_STATUS_COMPLETED,
                meta=build_file_meta(file_name="raw.nef", size=2048, user_meta={}),
            ),
            File(
                folder_id=docs.id,
                blob_id=blob.id,
                uploaded_by=user.id,
                name="notes.txt",
                parse_status=PARSE_STATUS_COMPLETED,
                meta=build_file_meta(file_name="notes.txt", size=12, user_meta={}),
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/files/?folder_id={photos.id}&recursive=true")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["name"] for item in body["items"]] == ["image.jpg", "raw.nef"]


def test_list_files_pagination(client, db_session, user, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    grant_access(db_session, user, photos, int(Permission.READ))
    bucket = BucketFactory.build()
    db_session.add(bucket)
    db_session.flush()
    blob = BlobFactory.build(bucket_id=bucket.id)
    db_session.add(blob)
    db_session.flush()
    names = ["e.bin", "d.bin", "c.bin", "b.bin", "a.bin"]
    for name in names:
        db_session.add(
            File(
                folder_id=photos.id,
                blob_id=blob.id,
                uploaded_by=user.id,
                name=name,
                parse_status=PARSE_STATUS_COMPLETED,
                meta=build_file_meta(file_name=name, size=100, user_meta={}),
            )
        )
    db_session.commit()

    r = client.get(
        f"/api/files/?folder_id={photos.id}&limit=2&offset=0&sort=name&order=asc"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert [item["name"] for item in body["items"]] == ["a.bin", "b.bin"]

    r2 = client.get(f"/api/files/?folder_id={photos.id}&limit=2&offset=4")
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2["items"]) == 1
    assert body2["items"][0]["name"] == "e.bin"


def test_list_files_rejects_invalid_sort(client, db_session, user, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    grant_access(db_session, user, photos, int(Permission.READ))

    response = client.get(f"/api/files/?folder_id={photos.id}&sort=nope")

    assert response.status_code == 400
    assert "sort must be one of" in response.json()["detail"]
