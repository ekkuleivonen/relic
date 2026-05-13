import uuid

import pytest
from api.app import app
from constants import META_EXTRACT_STATUS_COMPLETED
from database import get_db
from enums import BucketTier, Permission, UserRole
from fastapi.testclient import TestClient
from domain.files.meta import build_file_meta
from models import (
    Base,
    Blob,
    File,
    Folder,
    FolderAccess,
    User,
)
from services.auth import create_session_token
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import (
    BlobFactory,
    BucketFactory,
    FolderFactory,
    UserFactory,
)


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
    user = UserFactory.build(name="User", email="user@relic.local", role=UserRole.USER)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def admin(db_session):
    admin = UserFactory.build(
        name="Admin", email="admin@relic.local", role=UserRole.ADMIN
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def make_client(db_session, current_user: User) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    test_client.cookies.set("relic_session", create_session_token(current_user))
    return test_client


@pytest.fixture()
def client(db_session, user):
    test_client = make_client(db_session, user)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(db_session, admin):
    test_client = make_client(db_session, admin)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def root_folder(db_session):
    root = FolderFactory.build(name="", parent_id=None)
    db_session.add(root)
    db_session.commit()
    return root


def add_folder(db_session, parent: Folder, name: str) -> Folder:
    folder = FolderFactory.build(name=name, parent_id=parent.id)
    db_session.add(folder)
    db_session.commit()
    return folder


def grant(db_session, user: User, folder: Folder, permissions: int) -> None:
    db_session.add(
        FolderAccess(
            user_id=user.id,
            folder_id=folder.id,
            permissions=permissions,
        )
    )
    db_session.commit()


def add_file(db_session, folder: Folder, name: str, blob: Blob, user: User) -> File:
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        uploaded_by=user.id,
        name=name,
        meta_extract_status=META_EXTRACT_STATUS_COMPLETED,
        meta=build_file_meta(file_name=name, size=blob.size_bytes, user_meta={}),
    )
    db_session.add(file)
    db_session.commit()
    return file


@pytest.fixture()
def blob(db_session):
    bucket = BucketFactory.build()
    db_session.add(bucket)
    db_session.flush()
    blob = BlobFactory.build(bucket_id=bucket.id, refcount=0)
    db_session.add(blob)
    db_session.commit()
    return blob


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


def test_create_folder_succeeds_with_write_on_parent(
    client, db_session, user, root_folder
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))

    response = client.post(
        "/api/folders/",
        json={"parent_id": str(root_folder.id), "name": "photos"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "photos"
    assert body["parent_id"] == str(root_folder.id)
    assert body["path"] == "/photos"
    assert body["effective_permissions"] == int(Permission.READ | Permission.WRITE)


def test_create_folder_returns_403_when_user_has_only_read(
    client, db_session, user, root_folder
):
    grant(db_session, user, root_folder, int(Permission.READ))

    response = client.post(
        "/api/folders/",
        json={"parent_id": str(root_folder.id), "name": "photos"},
    )

    assert response.status_code == 403


def test_create_folder_returns_404_when_user_cannot_read_parent(
    client, db_session, root_folder
):
    response = client.post(
        "/api/folders/",
        json={"parent_id": str(root_folder.id), "name": "photos"},
    )

    assert response.status_code == 404


def test_create_folder_rejects_empty_name(client, db_session, user, root_folder):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))

    response = client.post(
        "/api/folders/",
        json={"parent_id": str(root_folder.id), "name": ""},
    )

    assert response.status_code == 422


def test_create_folder_conflicts_on_duplicate_name(
    client, db_session, user, root_folder
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    add_folder(db_session, root_folder, "photos")

    response = client.post(
        "/api/folders/",
        json={"parent_id": str(root_folder.id), "name": "photos"},
    )

    assert response.status_code == 409


def test_admin_can_create_folder_anywhere(admin_client, db_session, root_folder):
    response = admin_client.post(
        "/api/folders/",
        json={"parent_id": str(root_folder.id), "name": "photos"},
    )

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# RENAME (PATCH)
# ---------------------------------------------------------------------------


def test_rename_folder_succeeds_with_write(client, db_session, user, root_folder):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"name": "pictures"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "pictures"
    assert body["path"] == "/pictures"


def test_rename_folder_returns_403_without_write(client, db_session, user, root_folder):
    grant(db_session, user, root_folder, int(Permission.READ))
    photos = add_folder(db_session, root_folder, "photos")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"name": "pictures"},
    )

    assert response.status_code == 403


def test_rename_folder_returns_404_when_unreadable(client, db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"name": "pictures"},
    )

    assert response.status_code == 404


def test_cannot_rename_root(admin_client, db_session, root_folder):
    response = admin_client.patch(
        f"/api/folders/{root_folder.id}",
        json={"name": "newroot"},
    )

    assert response.status_code == 400


def test_rename_conflicts_on_existing_sibling(client, db_session, user, root_folder):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    add_folder(db_session, root_folder, "docs")
    photos = add_folder(db_session, root_folder, "photos")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"name": "docs"},
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# MOVE (PATCH parent_id)
# ---------------------------------------------------------------------------


def test_move_folder_succeeds(client, db_session, user, root_folder):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")
    archive = add_folder(db_session, root_folder, "archive")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"parent_id": str(archive.id)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parent_id"] == str(archive.id)
    assert body["path"] == "/archive/photos"


def test_move_folder_returns_403_without_write_on_destination(
    admin_client, db_session, root_folder
):
    # Create as admin so they exist
    photos = add_folder(db_session, root_folder, "photos")
    archive = add_folder(db_session, root_folder, "archive")
    # Create a normal user with WRITE on photos but not on archive
    bob = UserFactory.build(name="Bob", email="bob@relic.local")
    db_session.add(bob)
    db_session.commit()
    grant(db_session, bob, photos, int(Permission.READ | Permission.WRITE))
    grant(db_session, bob, archive, int(Permission.READ))

    bob_client = make_client(db_session, bob)
    try:
        response = bob_client.patch(
            f"/api/folders/{photos.id}",
            json={"parent_id": str(archive.id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_move_folder_rejects_descendant_destination(
    client, db_session, user, root_folder
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")
    raw = add_folder(db_session, photos, "raw")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"parent_id": str(raw.id)},
    )

    assert response.status_code == 400
    assert (
        "cycle" in response.json()["detail"].lower()
        or "descendant" in response.json()["detail"].lower()
    )


def test_move_folder_rejects_self_destination(client, db_session, user, root_folder):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"parent_id": str(photos.id)},
    )

    assert response.status_code == 400


def test_cannot_move_root(admin_client, db_session, root_folder):
    target = add_folder(db_session, root_folder, "target")

    response = admin_client.patch(
        f"/api/folders/{root_folder.id}",
        json={"parent_id": str(target.id)},
    )

    assert response.status_code == 400


def test_move_conflicts_on_name_collision_at_destination(
    client, db_session, user, root_folder
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    archive = add_folder(db_session, root_folder, "archive")
    add_folder(db_session, archive, "photos")
    photos = add_folder(db_session, root_folder, "photos")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"parent_id": str(archive.id)},
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# STORAGE POLICY (admin PATCH min_tier / cooldown_days)
# ---------------------------------------------------------------------------


def test_non_admin_cannot_patch_storage_policy(client, db_session, user, root_folder):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")

    response = client.patch(
        f"/api/folders/{photos.id}",
        json={"min_tier": 2},
    )

    assert response.status_code == 403


def test_admin_can_patch_folder_storage_policy(admin_client, db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")

    response = admin_client.patch(
        f"/api/folders/{photos.id}",
        json={"min_tier": 3, "cooldown_days": 30},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["min_tier"] == 3
    assert body["cooldown_days"] == 30
    assert body["effective_min_tier"] == 3
    assert body["effective_cooldown_days"] == 30
    db_session.refresh(photos)
    assert photos.min_tier == 3
    assert photos.cooldown_days == 30


def test_admin_can_patch_root_storage_policy(admin_client, db_session, root_folder):
    response = admin_client.patch(
        f"/api/folders/{root_folder.id}",
        json={"min_tier": 2, "cooldown_days": 14},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["min_tier"] == 2
    assert body["cooldown_days"] == 14
    assert body["effective_min_tier"] == 2
    assert body["effective_cooldown_days"] == 14


def test_admin_can_clear_cooldown_via_patch(admin_client, db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")
    root_folder.cooldown_days = 30
    photos.cooldown_days = 7
    db_session.commit()

    response = admin_client.patch(
        f"/api/folders/{photos.id}",
        json={"cooldown_days": None},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cooldown_days"] is None
    assert body["effective_cooldown_days"] == 30
    db_session.refresh(photos)
    assert photos.cooldown_days is None


def test_admin_cannot_set_root_min_tier_to_inherit(
    admin_client, db_session, root_folder
):
    response = admin_client.patch(
        f"/api/folders/{root_folder.id}",
        json={"min_tier": None},
    )
    assert response.status_code == 400


def test_admin_can_set_child_min_tier_to_inherit(admin_client, db_session, root_folder):
    root_folder.min_tier = int(BucketTier.WARM)
    photos = add_folder(db_session, root_folder, "photos")
    photos.min_tier = int(BucketTier.COLD)
    db_session.commit()

    response = admin_client.patch(
        f"/api/folders/{photos.id}",
        json={"min_tier": None},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["min_tier"] is None
    assert body["effective_min_tier"] == int(BucketTier.WARM)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_empty_folder_succeeds(client, db_session, user, root_folder):
    grant(
        db_session,
        user,
        root_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    photos = add_folder(db_session, root_folder, "photos")

    response = client.delete(f"/api/folders/{photos.id}")

    assert response.status_code == 204
    assert db_session.get(Folder, photos.id) is None


def test_delete_returns_403_without_delete_permission(
    client, db_session, user, root_folder
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")

    response = client.delete(f"/api/folders/{photos.id}")

    assert response.status_code == 403


def test_delete_returns_404_when_unreadable(client, db_session, root_folder):
    photos = add_folder(db_session, root_folder, "photos")

    response = client.delete(f"/api/folders/{photos.id}")

    assert response.status_code == 404


def test_cannot_delete_root(admin_client, db_session, root_folder):
    response = admin_client.delete(f"/api/folders/{root_folder.id}")

    assert response.status_code == 400


def test_delete_non_empty_folder_without_recursive_returns_409(
    client, db_session, user, root_folder
):
    grant(
        db_session,
        user,
        root_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    photos = add_folder(db_session, root_folder, "photos")
    add_folder(db_session, photos, "raw")

    response = client.delete(f"/api/folders/{photos.id}")

    assert response.status_code == 409


def test_delete_recursive_cascades_and_decrements_blob_refcount(
    client, db_session, user, root_folder, blob
):
    grant(
        db_session,
        user,
        root_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    photos = add_folder(db_session, root_folder, "photos")
    raw = add_folder(db_session, photos, "raw")
    add_file(db_session, photos, "image.jpg", blob, user)
    add_file(db_session, raw, "raw.nef", blob, user)
    blob.refcount = 2
    db_session.commit()

    response = client.delete(f"/api/folders/{photos.id}?recursive=true")

    assert response.status_code == 204
    assert db_session.get(Folder, photos.id) is None
    assert db_session.get(Folder, raw.id) is None
    db_session.refresh(blob)
    assert blob.refcount == 0


def test_delete_recursive_only_decrements_for_this_subtree(
    client, db_session, user, root_folder, blob
):
    grant(
        db_session,
        user,
        root_folder,
        int(Permission.READ | Permission.WRITE | Permission.DELETE),
    )
    photos = add_folder(db_session, root_folder, "photos")
    other = add_folder(db_session, root_folder, "other")
    add_file(db_session, photos, "image.jpg", blob, user)
    add_file(db_session, other, "shared.jpg", blob, user)
    blob.refcount = 2
    db_session.commit()

    response = client.delete(f"/api/folders/{photos.id}?recursive=true")

    assert response.status_code == 204
    db_session.refresh(blob)
    assert blob.refcount == 1


# ---------------------------------------------------------------------------
# DUPLICATE (POST /folders/{id}/copy)
# ---------------------------------------------------------------------------


def test_duplicate_folder_succeeds_with_read_source_and_write_dest(
    client, db_session, user, root_folder, blob
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")
    add_file(db_session, photos, "image.jpg", blob, user)
    blob.refcount = 1
    db_session.commit()

    response = client.post(
        f"/api/folders/{photos.id}/copy",
        json={
            "destination_parent_id": str(root_folder.id),
            "name": "photos copy",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "photos copy"
    assert body["parent_id"] == str(root_folder.id)
    db_session.refresh(blob)
    assert blob.refcount == 2


def test_duplicate_recursive_copies_subtree_and_increments_refcounts(
    client, db_session, user, root_folder, blob
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    photos = add_folder(db_session, root_folder, "photos")
    raw = add_folder(db_session, photos, "raw")
    add_file(db_session, photos, "image.jpg", blob, user)
    add_file(db_session, raw, "raw.nef", blob, user)
    blob.refcount = 2
    db_session.commit()

    response = client.post(
        f"/api/folders/{photos.id}/copy",
        json={
            "destination_parent_id": str(root_folder.id),
            "name": "photos copy",
            "recursive": True,
        },
    )

    assert response.status_code == 201, response.text
    db_session.refresh(blob)
    assert blob.refcount == 4
    new_id = uuid.UUID(response.json()["id"])
    cloned_root = db_session.get(Folder, new_id)
    assert cloned_root is not None
    cloned_raw = db_session.scalar(
        select(Folder).where(Folder.parent_id == cloned_root.id, Folder.name == "raw")
    )
    assert cloned_raw is not None


def test_duplicate_returns_403_without_write_on_destination(
    admin_client, db_session, root_folder
):
    photos = add_folder(db_session, root_folder, "photos")
    archive = add_folder(db_session, root_folder, "archive")
    bob = UserFactory.build(name="Bob", email="bob@relic.local")
    db_session.add(bob)
    db_session.commit()
    grant(db_session, bob, photos, int(Permission.READ))
    grant(db_session, bob, archive, int(Permission.READ))

    bob_client = make_client(db_session, bob)
    try:
        response = bob_client.post(
            f"/api/folders/{photos.id}/copy",
            json={
                "destination_parent_id": str(archive.id),
                "name": "photos copy",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_duplicate_conflicts_on_existing_name_at_destination(
    client, db_session, user, root_folder
):
    grant(db_session, user, root_folder, int(Permission.READ | Permission.WRITE))
    add_folder(db_session, root_folder, "photos copy")
    photos = add_folder(db_session, root_folder, "photos")

    response = client.post(
        f"/api/folders/{photos.id}/copy",
        json={
            "destination_parent_id": str(root_folder.id),
            "name": "photos copy",
        },
    )

    assert response.status_code == 409
