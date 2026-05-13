"""Live S3 gateway compatibility smoke harness.

Run against a local Relic stack, not the in-memory pytest app. The harness uses
the same Relic presigned SigV4 query URLs the gateway currently accepts, while
keeping the checks shaped like S3 client compatibility flows: bucket discovery,
bucket preflight, object upload, prefix/delimiter browsing, pagination, HEAD,
and GET.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings as S
from services import s3_signing


@dataclass(frozen=True)
class CompatConfig:
    api_url: str
    email: str
    password: str
    bucket_name: str
    keep_data: bool

    @property
    def host(self) -> str:
        parsed = urllib.parse.urlparse(self.api_url)
        return parsed.netloc


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        body: bytes | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected: set[int] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        url = self.absolute_url(path_or_url)
        request_headers = dict(headers or {})
        payload = body
        if json_body is not None:
            payload = json.dumps(json_body).encode()
            request_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url,
            data=payload,
            headers=request_headers,
            method=method,
        )
        try:
            with self.opener.open(req, timeout=30) as response:
                status = response.status
                response_body = response.read()
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_body = exc.read()
            response_headers = dict(exc.headers.items())

        allowed = expected or {200}
        if status not in allowed:
            raise RuntimeError(
                f"{method} {url} returned {status}, expected {sorted(allowed)}: "
                f"{response_body.decode(errors='replace')}"
            )
        return status, response_headers, response_body

    def absolute_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return urllib.parse.urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))


def main() -> None:
    config = parse_args()
    client = HttpClient(config.api_url)
    run_compat(config, client)


def parse_args() -> CompatConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--email", default="admin@relic.local")
    parser.add_argument("--password", default="relic-admin")
    parser.add_argument(
        "--bucket-name",
        default=f"compat-{int(time.time())}-{uuid.uuid4().hex[:8]}",
        help="Top-level Relic folder to use as the S3 bucket.",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep the generated top-level folder instead of deleting it.",
    )
    args = parser.parse_args()
    return CompatConfig(
        api_url=args.api_url,
        email=args.email,
        password=args.password,
        bucket_name=args.bucket_name,
        keep_data=args.keep_data,
    )


def run_compat(config: CompatConfig, client: HttpClient) -> None:
    print(f"Relic API: {config.api_url}")
    user = login(client, config)
    print(f"Logged in as {user['email']} ({user['id']})")

    require_bucket_backend(client)
    root = client_json(client, "GET", "/api/folders/tree")
    bucket = client_json(
        client,
        "POST",
        "/api/folders/",
        json_body={"parent_id": root["id"], "name": config.bucket_name},
        expected={201},
    )
    print(f"Created S3 bucket folder: {config.bucket_name}")

    try:
        nested = client_json(
            client,
            "POST",
            "/api/folders/",
            json_body={"parent_id": bucket["id"], "name": "2026"},
            expected={201},
        )
        raw = client_json(
            client,
            "POST",
            "/api/folders/",
            json_body={"parent_id": nested["id"], "name": "raw"},
            expected={201},
        )

        put_presigned(client, bucket["id"], "cover.txt", b"cover")
        put_presigned(client, nested["id"], "cat.txt", b"cat")
        put_presigned(client, raw["id"], "dog.txt", b"dog")
        print("Uploaded root and nested objects through presigned PUT")

        assert_list_buckets(client, config, user["id"])
        assert_head_bucket(client, config, user["id"])
        assert_list_objects(client, config, user["id"])
        assert_pagination(client, config, user["id"])
        assert_head_and_get(client, config, user["id"])
        assert_multipart_upload(client, config, user["id"])
        print("S3 compatibility smoke checks passed")
    finally:
        if config.keep_data:
            print(f"Keeping generated folder: {config.bucket_name}")
        else:
            client.request(
                "DELETE",
                f"/api/folders/{bucket['id']}?recursive=true",
                expected={204},
            )
            print(f"Deleted generated folder: {config.bucket_name}")


def login(client: HttpClient, config: CompatConfig) -> dict[str, Any]:
    response = client_json(
        client,
        "POST",
        "/api/auth/login",
        json_body={"email": config.email, "password": config.password},
    )
    return response["user"]


def require_bucket_backend(client: HttpClient) -> None:
    buckets = client_json(client, "GET", "/api/buckets/")
    if not buckets:
        raise RuntimeError(
            "No physical bucket backends are registered. Register and probe at "
            "least one bucket in Admin > Buckets before running compatibility."
        )
    healthy = [
        bucket
        for bucket in buckets
        if all(
            bucket.get(name) is not None
            for name in (
                "probe_latency_put_ms",
                "probe_latency_head_ms",
                "probe_latency_get_ms",
                "probe_latency_delete_ms",
            )
        )
    ]
    if not healthy:
        print("Warning: no bucket backend has a full probe snapshot yet.")


def put_presigned(
    client: HttpClient, folder_id: str, filename: str, content: bytes
) -> None:
    signed = client_json(
        client,
        "POST",
        "/api/uploads/presign",
        json_body={"folder_id": folder_id, "filename": filename, "meta": {}},
    )
    client.request("PUT", signed["url"], body=content, headers=signed["headers"])


def assert_list_buckets(client: HttpClient, config: CompatConfig, user_id: str) -> None:
    signed = s3_signing.sign_service_url(
        method="GET",
        headers={},
        user_id=uuid.UUID(user_id),
        host=config.host,
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )
    _, _, body = client.request("GET", signed.url, headers=signed.headers)
    names = xml_texts(body, ".//Bucket/Name")
    assert_contains(names, config.bucket_name, "ListBuckets should include compat bucket")
    print("ListBuckets OK")


def assert_head_bucket(client: HttpClient, config: CompatConfig, user_id: str) -> None:
    signed = sign_bucket(config, user_id, "HEAD")
    client.request("HEAD", signed.url, headers=signed.headers)
    print("HeadBucket OK")


def assert_list_objects(client: HttpClient, config: CompatConfig, user_id: str) -> None:
    signed = sign_bucket(
        config,
        user_id,
        "GET",
        {"list-type": "2", "delimiter": "/"},
    )
    _, _, body = client.request("GET", signed.url, headers=signed.headers)
    assert_equal(
        xml_texts(body, ".//Contents/Key"),
        ["cover.txt"],
        "ListObjectsV2 delimiter root contents",
    )
    assert_equal(
        xml_texts(body, ".//CommonPrefixes/Prefix"),
        ["2026/"],
        "ListObjectsV2 delimiter common prefixes",
    )

    prefixed = sign_bucket(
        config,
        user_id,
        "GET",
        {"list-type": "2", "prefix": "2026/", "delimiter": "/"},
    )
    _, _, prefixed_body = client.request(
        "GET", prefixed.url, headers=prefixed.headers
    )
    assert_equal(
        xml_texts(prefixed_body, ".//Contents/Key"),
        ["2026/cat.txt"],
        "ListObjectsV2 prefix contents",
    )
    assert_equal(
        xml_texts(prefixed_body, ".//CommonPrefixes/Prefix"),
        ["2026/raw/"],
        "ListObjectsV2 prefix common prefixes",
    )
    print("ListObjectsV2 prefix/delimiter OK")


def assert_pagination(client: HttpClient, config: CompatConfig, user_id: str) -> None:
    first = sign_bucket(
        config,
        user_id,
        "GET",
        {"list-type": "2", "max-keys": "1"},
    )
    _, _, first_body = client.request("GET", first.url, headers=first.headers)
    assert_equal(xml_texts(first_body, ".//Contents/Key"), ["2026/cat.txt"], "first page")
    assert_equal(xml_texts(first_body, ".//IsTruncated"), ["true"], "first page truncated")
    token = xml_texts(first_body, ".//NextContinuationToken")[0]

    second = sign_bucket(
        config,
        user_id,
        "GET",
        {"list-type": "2", "max-keys": "1", "continuation-token": token},
    )
    _, _, second_body = client.request("GET", second.url, headers=second.headers)
    assert_equal(xml_texts(second_body, ".//Contents/Key"), ["2026/raw/dog.txt"], "second page")
    print("ListObjectsV2 pagination OK")


def assert_head_and_get(client: HttpClient, config: CompatConfig, user_id: str) -> None:
    head = s3_signing.sign_request_url(
        method="HEAD",
        bucket=config.bucket_name,
        key="cover.txt",
        headers={},
        user_id=uuid.UUID(user_id),
        host=config.host,
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )
    client.request("HEAD", head.url, headers=head.headers)

    get = s3_signing.sign_get_url(
        bucket=config.bucket_name,
        key="cover.txt",
        user_id=uuid.UUID(user_id),
        host=config.host,
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )
    _, _, body = client.request("GET", get.url, headers=get.headers)
    assert_equal(body, b"cover", "GetObject body")
    print("HeadObject/GetObject OK")


def assert_multipart_upload(
    client: HttpClient, config: CompatConfig, user_id: str
) -> None:
    upload_id: str | None = None
    create = s3_signing.sign_request_url(
        method="POST",
        bucket=config.bucket_name,
        key="multipart.bin",
        headers={},
        user_id=uuid.UUID(user_id),
        host=config.host,
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploads": ""},
    )
    try:
        _, _, create_body = client.request("POST", create.url, headers=create.headers)
        upload_id = xml_texts(create_body, ".//UploadId")[0]

        completed_parts: list[tuple[int, str]] = []
        for part_number, content in [(1, b"multi-"), (2, b"part")]:
            part = s3_signing.sign_request_url(
                method="PUT",
                bucket=config.bucket_name,
                key="multipart.bin",
                headers={},
                user_id=uuid.UUID(user_id),
                host=config.host,
                ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
                query_params={
                    "partNumber": str(part_number),
                    "uploadId": upload_id,
                },
            )
            _, headers, _ = client.request(
                "PUT",
                part.url,
                body=content,
                headers=part.headers,
            )
            completed_parts.append((part_number, header_value(headers, "ETag")))

        complete_body = (
            "<CompleteMultipartUpload>"
            + "".join(
                f"<Part><PartNumber>{part_number}</PartNumber><ETag>{etag}</ETag></Part>"
                for part_number, etag in completed_parts
            )
            + "</CompleteMultipartUpload>"
        ).encode()
        complete = s3_signing.sign_request_url(
            method="POST",
            bucket=config.bucket_name,
            key="multipart.bin",
            headers={},
            user_id=uuid.UUID(user_id),
            host=config.host,
            ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
            query_params={"uploadId": upload_id},
        )
        client.request(
            "POST",
            complete.url,
            body=complete_body,
            headers=complete.headers,
        )
        upload_id = None

        get = s3_signing.sign_get_url(
            bucket=config.bucket_name,
            key="multipart.bin",
            user_id=uuid.UUID(user_id),
            host=config.host,
            ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        )
        _, _, body = client.request("GET", get.url, headers=get.headers)
        assert_equal(body, b"multi-part", "multipart GetObject body")
        print("Multipart upload OK")
    finally:
        if upload_id is not None:
            abort_multipart_upload(client, config, user_id, upload_id)


def abort_multipart_upload(
    client: HttpClient, config: CompatConfig, user_id: str, upload_id: str
) -> None:
    abort = s3_signing.sign_request_url(
        method="DELETE",
        bucket=config.bucket_name,
        key="multipart.bin",
        headers={},
        user_id=uuid.UUID(user_id),
        host=config.host,
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params={"uploadId": upload_id},
    )
    client.request("DELETE", abort.url, headers=abort.headers, expected={204, 404})


def header_value(headers: dict[str, str], name: str) -> str:
    for header_name, value in headers.items():
        if header_name.lower() == name.lower():
            return value
    raise KeyError(name)


def sign_bucket(
    config: CompatConfig,
    user_id: str,
    method: str,
    query_params: dict[str, str] | None = None,
) -> s3_signing.SignedUrl:
    return s3_signing.sign_bucket_url(
        method=method,
        bucket=config.bucket_name,
        headers={},
        user_id=uuid.UUID(user_id),
        host=config.host,
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
        query_params=query_params,
    )


def client_json(
    client: HttpClient,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    expected: set[int] | None = None,
) -> Any:
    _, _, body = client.request(method, path, json_body=json_body, expected=expected)
    return json.loads(body.decode())


def xml_texts(body: bytes, path: str) -> list[str]:
    root = ET.fromstring(body)
    return [element.text or "" for element in root.findall(path)]


def assert_contains(values: list[str], expected: str, message: str) -> None:
    if expected not in values:
        raise AssertionError(f"{message}: expected {expected!r} in {values!r}")


def assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


if __name__ == "__main__":
    main()
