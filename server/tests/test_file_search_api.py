"""Search + facets endpoints over the canonical FileMeta schema."""

import pytest
from api.app import app
from infra.db.engine import get_db
from enums import Permission, UserRole
from fastapi.testclient import TestClient
from infra.db.models import (
    Base,
    Blob,
    File,
    Folder,
    FolderAccess,
    User,
)
from infra.db.stores.auth import create_session_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import BucketFactory, UserFactory



@pytest.fixture()
def user(db_session):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def admin(db_session):
    admin = UserFactory.build(email="admin@relic.local", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.commit()
    return admin


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
def admin_client(db_session, admin):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(admin))
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def bucket(db_session):
    bucket = BucketFactory.build(name="hot")
    db_session.add(bucket)
    db_session.commit()
    return bucket


@pytest.fixture()
def root_folder(db_session):
    root = Folder(name="", parent_id=None)
    db_session.add(root)
    db_session.commit()
    return root


@pytest.fixture()
def photos_folder(db_session, root_folder):
    folder = Folder(
        name="photos",
        parent_id=root_folder.id,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def raw_folder(db_session, photos_folder):
    folder = Folder(
        name="raw",
        parent_id=photos_folder.id,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


@pytest.fixture()
def archives_folder(db_session, root_folder):
    folder = Folder(
        name="archives",
        parent_id=root_folder.id,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


def grant(db_session, user, folder, permissions: int) -> None:
    db_session.add(
        FolderAccess(actor_id=user.id, folder_id=folder.id, permissions=int(permissions))
    )
    db_session.commit()


def make_blob(
    db_session,
    *,
    bucket,
    content_hash: int,
    size_bytes: int = 9,
    mimetype: str = "application/octet-stream",
    extension: str = "",
) -> Blob:
    blob = Blob(
        bucket_id=bucket.id,
        bucket_key=f"objects/{content_hash}",
        content_hash=content_hash.to_bytes(32, "big"),
        size_bytes=size_bytes,
        mimetype=mimetype,
        extension=extension,
        refcount=1,
    )
    db_session.add(blob)
    db_session.commit()
    return blob


def make_file(
    db_session,
    *,
    folder: Folder,
    blob: Blob,
    user: User,
    name: str,
    mimetype: str = "application/octet-stream",
    size: int | None = None,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
    summary: str | None = None,
    kvs: dict | None = None,
) -> File:
    user_meta: dict = {}
    if tags is not None:
        user_meta["tags"] = tags
    if keywords is not None:
        user_meta["keywords"] = keywords
    if summary is not None:
        user_meta["summary"] = summary
    if kvs is not None:
        user_meta["kvs"] = kvs
    if size is not None:
        blob.size_bytes = size
    blob.mimetype = mimetype
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    blob.extension = extension
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        actor_id=user.id,
        name=name,
        meta=user_meta,
    )
    db_session.add(file)
    db_session.commit()
    return file


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------


def test_search_returns_only_visible_files(
    client, db_session, user, bucket, photos_folder, archives_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=1)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=2)
    make_file(db_session, folder=photos_folder, blob=blob_a, user=user, name="cat.jpg")
    make_file(
        db_session, folder=archives_folder, blob=blob_b, user=user, name="hidden.bin"
    )

    response = client.get("/api/files/search")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "cat.jpg"


def test_search_paginates_with_stable_total(
    client, db_session, user, bucket, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    for index in range(12):
        blob = make_blob(db_session, bucket=bucket, content_hash=100 + index)
        make_file(
            db_session,
            folder=photos_folder,
            blob=blob,
            user=user,
            name=f"item-{index:02d}.bin",
        )

    response = client.get(
        "/api/files/search",
        params={"sort": "name", "order": "asc", "limit": 5, "offset": 5},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 12
    assert [item["name"] for item in body["items"]] == [
        "item-05.bin",
        "item-06.bin",
        "item-07.bin",
        "item-08.bin",
        "item-09.bin",
    ]


def test_search_q_matches_name_summary_and_keywords(
    client, db_session, user, bucket, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=10)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=11)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=12)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="invoice-2026.pdf",
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="report.pdf",
        summary="Quarterly invoice summary",
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_c,
        user=user,
        name="random.pdf",
        keywords=["INVOICE", "billing"],
    )

    response = client.get("/api/files/search?q=invoice")

    assert response.status_code == 200, response.text
    body = response.json()
    names = sorted(item["name"] for item in body["items"])
    assert names == ["invoice-2026.pdf", "random.pdf", "report.pdf"]


def test_search_q_requires_all_terms(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=20)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=21)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="quarterly-invoice.pdf",
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="invoice.pdf",
    )

    response = client.get("/api/files/search?q=quarterly%20invoice")

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "quarterly-invoice.pdf"


def test_search_tag_any_of(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=30)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=31)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=32)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.jpg",
        tags=["photo", "large"],
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.jpg",
        tags=["screenshot"],
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_c,
        user=user,
        name="c.pdf",
        tags=["document"],
    )

    response = client.get("/api/files/search?tag=photo&tag=screenshot")

    body = response.json()
    names = sorted(item["name"] for item in body["items"])
    assert names == ["a.jpg", "b.jpg"]


def test_search_tag_require_all(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=40)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=41)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.jpg",
        tags=["photo", "large"],
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.jpg",
        tags=["photo"],
    )

    response = client.get("/api/files/search?tag=photo&tag=large&require_all_tags=true")

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "a.jpg"


def test_search_mimetype_and_extension_filters(
    client, db_session, user, bucket, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=50)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=51)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=52)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.jpg",
        mimetype="image/jpeg",
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.png",
        mimetype="image/png",
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_c,
        user=user,
        name="c.pdf",
        mimetype="application/pdf",
    )

    response = client.get("/api/files/search?mimetype=image/jpeg&mimetype=image/png")
    body = response.json()
    assert sorted(item["name"] for item in body["items"]) == ["a.jpg", "b.png"]

    response = client.get("/api/files/search?extension=pdf")
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["c.pdf"]


def test_search_size_range(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=60, size_bytes=100)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=61, size_bytes=10_000)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=62, size_bytes=1_000_000)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="tiny.bin",
        size=100,
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="medium.bin",
        size=10_000,
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_c,
        user=user,
        name="large.bin",
        size=1_000_000,
    )

    response = client.get("/api/files/search?min_size=200&max_size=500000")
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["medium.bin"]


def test_search_kvs_range(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=70)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=71)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=72)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.csv",
        kvs={"row_count": 50},
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.csv",
        kvs={"row_count": 5_000},
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_c,
        user=user,
        name="c.csv",
        kvs={"row_count": 50_000},
    )

    response = client.get(
        "/api/files/search?kv=row_count:gte:1000&kv=row_count:lte:10000"
    )
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["b.csv"]


def test_search_kvs_eq_handles_strings(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=80)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=81)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.flac",
        kvs={"codec": "flac"},
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.mp3",
        kvs={"codec": "mp3"},
    )

    response = client.get("/api/files/search?kv=codec:eq:flac")
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["a.flac"]


def test_search_kvs_invalid_op_returns_400(client):
    response = client.get("/api/files/search?kv=row_count:contains:bad")
    assert response.status_code == 400


def test_search_folder_scope_and_recursive(
    client, db_session, user, bucket, photos_folder, raw_folder, archives_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    grant(db_session, user, archives_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=90)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=91)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=92)
    make_file(db_session, folder=photos_folder, blob=blob_a, user=user, name="top.jpg")
    make_file(db_session, folder=raw_folder, blob=blob_b, user=user, name="nested.jpg")
    make_file(
        db_session, folder=archives_folder, blob=blob_c, user=user, name="other.bin"
    )

    response = client.get(f"/api/files/search?folder_id={photos_folder.id}")
    body = response.json()
    assert sorted(item["name"] for item in body["items"]) == ["top.jpg"]

    response = client.get(
        f"/api/files/search?folder_id={photos_folder.id}&recursive=true"
    )
    body = response.json()
    assert sorted(item["name"] for item in body["items"]) == ["nested.jpg", "top.jpg"]


def test_search_pagination_and_sort(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    for index in range(5):
        blob = make_blob(
            db_session, bucket=bucket, content_hash=100 + index, size_bytes=index * 1000
        )
        make_file(
            db_session,
            folder=photos_folder,
            blob=blob,
            user=user,
            name=f"file-{index}.bin",
            size=index * 1000,
        )

    response = client.get("/api/files/search?sort=size&order=asc&limit=2&offset=0")
    body = response.json()
    assert body["total"] == 5
    assert [item["name"] for item in body["items"]] == ["file-0.bin", "file-1.bin"]

    response = client.get("/api/files/search?sort=size&order=asc&limit=2&offset=2")
    body = response.json()
    assert [item["name"] for item in body["items"]] == ["file-2.bin", "file-3.bin"]


def test_search_admin_sees_everything(
    admin_client, db_session, admin, bucket, photos_folder, archives_folder
):
    blob_a = make_blob(db_session, bucket=bucket, content_hash=200)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=201)
    make_file(db_session, folder=photos_folder, blob=blob_a, user=admin, name="x.jpg")
    make_file(db_session, folder=archives_folder, blob=blob_b, user=admin, name="y.bin")

    response = admin_client.get("/api/files/search")
    body = response.json()
    assert body["total"] == 2


# ---------------------------------------------------------------------------
# /facets
# ---------------------------------------------------------------------------


def test_facets_basic_counts(client, db_session, user, bucket, photos_folder):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=300)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=301)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=302)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.jpg",
        mimetype="image/jpeg",
        tags=["photo", "large"],
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.jpg",
        mimetype="image/jpeg",
        tags=["photo"],
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_c,
        user=user,
        name="c.pdf",
        mimetype="application/pdf",
        tags=["document"],
    )

    response = client.get("/api/files/facets")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    tag_counts = {item["value"]: item["count"] for item in body["tags"]}
    assert tag_counts == {"photo": 2, "document": 1, "large": 1}
    mime_counts = {item["value"]: item["count"] for item in body["mimetypes"]}
    assert mime_counts == {"image/jpeg": 2, "application/pdf": 1}
    ext_counts = {item["value"]: item["count"] for item in body["extensions"]}
    assert ext_counts == {"jpg": 2, "pdf": 1}


def test_facets_keep_other_tag_values_visible(
    client, db_session, user, bucket, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=400)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=401)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.jpg",
        tags=["photo"],
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.pdf",
        tags=["document"],
    )

    response = client.get("/api/files/facets?tag=photo")
    body = response.json()
    assert body["total"] == 1
    tag_counts = {item["value"]: item["count"] for item in body["tags"]}
    assert tag_counts == {"photo": 1, "document": 1}


def test_facets_expose_kvs_keys_in_dataset(
    client, db_session, user, bucket, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=600)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=601)
    blob_c = make_blob(db_session, bucket=bucket, content_hash=602)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.csv",
        kvs={"row_count": 100, "column_count": 5},
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.csv",
        kvs={"row_count": 200},
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_c,
        user=user,
        name="c.mp4",
        kvs={"duration_seconds": 600},
    )

    response = client.get("/api/files/facets")
    body = response.json()
    counts = {item["value"]: item["count"] for item in body["kvs_keys"]}
    assert counts == {"row_count": 2, "column_count": 1, "duration_seconds": 1}


def test_facets_kvs_keys_ignore_active_kvs_filter(
    client, db_session, user, bucket, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=620)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=621)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.csv",
        kvs={"row_count": 100},
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.mp4",
        kvs={"duration_seconds": 600},
    )

    response = client.get("/api/files/facets?kv=row_count:gte:50")
    body = response.json()
    counts = {item["value"]: item["count"] for item in body["kvs_keys"]}
    assert counts == {"row_count": 1, "duration_seconds": 1}
    assert body["total"] == 1


def test_facets_mimetype_with_active_mimetype_filter(
    client, db_session, user, bucket, photos_folder
):
    grant(db_session, user, photos_folder, int(Permission.READ))
    blob_a = make_blob(db_session, bucket=bucket, content_hash=500)
    blob_b = make_blob(db_session, bucket=bucket, content_hash=501)
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_a,
        user=user,
        name="a.jpg",
        mimetype="image/jpeg",
    )
    make_file(
        db_session,
        folder=photos_folder,
        blob=blob_b,
        user=user,
        name="b.png",
        mimetype="image/png",
    )

    response = client.get("/api/files/facets?mimetype=image/jpeg")
    body = response.json()
    mime_counts = {item["value"]: item["count"] for item in body["mimetypes"]}
    assert mime_counts == {"image/jpeg": 1, "image/png": 1}
    assert body["total"] == 1
