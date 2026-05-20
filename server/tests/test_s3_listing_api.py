import hashlib
import xml.etree.ElementTree as ET

import pytest
from api.app import app
from infra.db.engine import get_db
from enums import Permission
from fastapi.testclient import TestClient
from infra.db.models import Base, Blob, File, Folder, FolderAccess
from application.gateway import object_signing
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import StorageBackendFactory, UserFactory



@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def user(db_session):
    user = UserFactory.build(email="user@relic.local")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def root_folder(db_session):
    root = Folder(
        name="",
        parent_id=None,
    )
    db_session.add(root)
    db_session.commit()
    return root


def add_folder(db_session, name: str, parent: Folder) -> Folder:
    folder = Folder(
        name=name,
        parent_id=parent.id,
    )
    db_session.add(folder)
    db_session.commit()
    return folder


def grant(db_session, user, folder: Folder, permissions: int = int(Permission.READ)):
    db_session.add(
        FolderAccess(actor_id=user.id, folder_id=folder.id, permissions=permissions)
    )
    db_session.commit()


def add_file(db_session, folder: Folder, user, filename: str, body: bytes) -> File:
    physical_bucket = db_session.query(StorageBackendFactory._meta.model).first()
    if physical_bucket is None:
        physical_bucket = StorageBackendFactory.build(name="hot")
        db_session.add(physical_bucket)
        db_session.flush()

    digest = hashlib.sha256(body).digest()
    blob = Blob(
        storage_backend_id=physical_bucket.id,
        bucket_key=f"objects/{digest.hex()}",
        content_hash=digest,
        size_bytes=len(body),
        refcount=1,
    )
    db_session.add(blob)
    db_session.flush()
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        actor_id=user.id,
        name=filename,
        meta={},
    )
    db_session.add(file)
    db_session.commit()
    return file


def signed_service_get(user, query_params: dict[str, str] | None = None):
    return object_signing.sign_service_url(
        method="GET",
        headers={},
        user_id=user.id,
        host="testserver",
        query_params=query_params,
    )


def signed_bucket_request(
    method: str,
    user,
    bucket: str,
    query_params: dict[str, str] | None = None,
):
    return object_signing.sign_bucket_url(
        method=method,
        bucket=bucket,
        headers={},
        user_id=user.id,
        host="testserver",
        query_params=query_params,
    )


def xml_texts(response, tag: str) -> list[str]:
    root = ET.fromstring(response.text)
    return [element.text or "" for element in root.findall(f".//{tag}")]


def common_prefix_texts(response) -> list[str]:
    root = ET.fromstring(response.text)
    return [
        element.findtext("Prefix") or ""
        for element in root.findall(".//CommonPrefixes")
    ]


def test_list_buckets_returns_visible_top_level_folders(
    client, db_session, user, root_folder
):
    photos = add_folder(db_session, "photos", root_folder)
    add_folder(db_session, "private", root_folder)
    grant(db_session, user, photos)
    signed = signed_service_get(user)

    response = client.get(signed.url, headers=signed.headers)

    assert response.status_code == 200
    assert xml_texts(response, "Name") == ["photos"]


def test_head_bucket_checks_visibility(client, db_session, user, root_folder):
    photos = add_folder(db_session, "photos", root_folder)
    add_folder(db_session, "private", root_folder)
    grant(db_session, user, photos)

    visible = signed_bucket_request("HEAD", user, "photos")
    hidden = signed_bucket_request("HEAD", user, "private")

    assert client.head(visible.url, headers=visible.headers).status_code == 200
    assert client.head(hidden.url, headers=hidden.headers).status_code == 404


def test_list_objects_v2_returns_contents_and_common_prefixes(
    client, db_session, user, root_folder
):
    photos = add_folder(db_session, "photos", root_folder)
    year = add_folder(db_session, "2026", photos)
    raw = add_folder(db_session, "raw", year)
    grant(db_session, user, photos)
    add_file(db_session, photos, user, "cover.jpg", b"cover")
    add_file(db_session, year, user, "cat.jpg", b"cat")
    add_file(db_session, raw, user, "dog.jpg", b"dog")
    signed = signed_bucket_request(
        "GET",
        user,
        "photos",
        {"list-type": "2", "delimiter": "/"},
    )

    response = client.get(signed.url, headers=signed.headers)

    assert response.status_code == 200, response.text
    assert xml_texts(response, "Key") == ["cover.jpg"]
    assert common_prefix_texts(response) == ["2026/"]
    assert xml_texts(response, "IsTruncated") == ["false"]


def test_list_objects_v2_supports_prefix_and_delimiter(
    client, db_session, user, root_folder
):
    photos = add_folder(db_session, "photos", root_folder)
    year = add_folder(db_session, "2026", photos)
    raw = add_folder(db_session, "raw", year)
    grant(db_session, user, photos)
    add_file(db_session, photos, user, "cover.jpg", b"cover")
    add_file(db_session, year, user, "cat.jpg", b"cat")
    add_file(db_session, raw, user, "dog.jpg", b"dog")
    signed = signed_bucket_request(
        "GET",
        user,
        "photos",
        {"list-type": "2", "prefix": "2026/", "delimiter": "/"},
    )

    response = client.get(signed.url, headers=signed.headers)

    assert response.status_code == 200, response.text
    assert xml_texts(response, "Key") == ["2026/cat.jpg"]
    assert common_prefix_texts(response) == ["2026/raw/"]


def test_list_objects_v2_paginates_with_continuation_token(
    client, db_session, user, root_folder
):
    photos = add_folder(db_session, "photos", root_folder)
    grant(db_session, user, photos)
    add_file(db_session, photos, user, "a.txt", b"a")
    add_file(db_session, photos, user, "b.txt", b"b")
    first = signed_bucket_request(
        "GET",
        user,
        "photos",
        {"list-type": "2", "max-keys": "1"},
    )

    first_response = client.get(first.url, headers=first.headers)

    assert first_response.status_code == 200, first_response.text
    assert xml_texts(first_response, "Key") == ["a.txt"]
    assert xml_texts(first_response, "IsTruncated") == ["true"]
    token = xml_texts(first_response, "NextContinuationToken")[0]
    second = signed_bucket_request(
        "GET",
        user,
        "photos",
        {"list-type": "2", "max-keys": "1", "continuation-token": token},
    )

    second_response = client.get(second.url, headers=second.headers)

    assert second_response.status_code == 200, second_response.text
    assert xml_texts(second_response, "Key") == ["b.txt"]
    assert xml_texts(second_response, "IsTruncated") == ["false"]
