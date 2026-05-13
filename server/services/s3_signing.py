import datetime as dt
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from fastapi import Request

import settings as S

ALGORITHM = "AWS4-HMAC-SHA256"
SERVICE = "s3"
TERMINATOR = "aws4_request"
UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"
USER_BINDING_HEADER = "x-amz-meta-relic-user"


@dataclass(frozen=True)
class SignedUrl:
    url: str
    headers: dict[str, str]
    expires_at: dt.datetime


@dataclass(frozen=True)
class VerifiedRequest:
    user_id: uuid.UUID
    key_id: str
    signed_headers: dict[str, str]


class S3SigningError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def sign_request_url(
    *,
    method: str,
    bucket: str,
    key: str,
    headers: dict[str, str],
    user_id: uuid.UUID,
    host: str,
    ttl_seconds: int | None = None,
    query_params: dict[str, str] | None = None,
) -> SignedUrl:
    ttl = ttl_seconds if ttl_seconds is not None else S.RELIC_SIGNING_TTL_SECONDS
    request_time = now_utc()
    date_stamp = request_time.strftime("%Y%m%d")
    amz_date = request_time.strftime("%Y%m%dT%H%M%SZ")
    expires_at = request_time + dt.timedelta(seconds=ttl)
    key_id = S.RELIC_SIGNING_CURRENT_KEY_ID
    signed_headers = normalize_headers(
        {
            **headers,
            "host": host,
            "x-amz-content-sha256": UNSIGNED_PAYLOAD,
            USER_BINDING_HEADER: str(user_id),
        }
    )
    signed_header_names = ";".join(sorted(signed_headers))
    credential = f"{key_id}/{date_stamp}/{S.RELIC_SIGNING_REGION}/{SERVICE}/{TERMINATOR}"
    canonical_uri = canonical_object_uri(bucket, key)
    signed_query_params = {
        **(query_params or {}),
        "X-Amz-Algorithm": ALGORITHM,
        "X-Amz-Credential": credential,
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(ttl),
        "X-Amz-SignedHeaders": signed_header_names,
    }
    canonical_request = build_canonical_request(
        method=method,
        canonical_uri=canonical_uri,
        query_params=signed_query_params,
        headers=signed_headers,
        signed_header_names=signed_header_names,
    )
    signature = sign_string(
        secret=S.RELIC_SIGNING_KEYS[key_id],
        date_stamp=date_stamp,
        string_to_sign=build_string_to_sign(
            amz_date=amz_date,
            credential_scope=credential_scope(date_stamp),
            canonical_request=canonical_request,
        ),
    )
    signed_query_params["X-Amz-Signature"] = signature
    url = f"{canonical_uri}?{canonical_query_string(signed_query_params)}"
    response_headers = {
        name: value for name, value in signed_headers.items() if name != "host"
    }
    return SignedUrl(url=url, headers=response_headers, expires_at=expires_at)


def sign_service_url(
    *,
    method: str,
    headers: dict[str, str],
    user_id: uuid.UUID,
    host: str,
    ttl_seconds: int | None = None,
    query_params: dict[str, str] | None = None,
) -> SignedUrl:
    return sign_request_path_url(
        method=method,
        canonical_uri="/s3/",
        headers=headers,
        user_id=user_id,
        host=host,
        ttl_seconds=ttl_seconds,
        query_params=query_params,
    )


def sign_bucket_url(
    *,
    method: str,
    bucket: str,
    headers: dict[str, str],
    user_id: uuid.UUID,
    host: str,
    ttl_seconds: int | None = None,
    query_params: dict[str, str] | None = None,
) -> SignedUrl:
    return sign_request_path_url(
        method=method,
        canonical_uri=canonical_bucket_uri(bucket),
        headers=headers,
        user_id=user_id,
        host=host,
        ttl_seconds=ttl_seconds,
        query_params=query_params,
    )


def sign_request_path_url(
    *,
    method: str,
    canonical_uri: str,
    headers: dict[str, str],
    user_id: uuid.UUID,
    host: str,
    ttl_seconds: int | None = None,
    query_params: dict[str, str] | None = None,
) -> SignedUrl:
    ttl = ttl_seconds if ttl_seconds is not None else S.RELIC_SIGNING_TTL_SECONDS
    request_time = now_utc()
    date_stamp = request_time.strftime("%Y%m%d")
    amz_date = request_time.strftime("%Y%m%dT%H%M%SZ")
    expires_at = request_time + dt.timedelta(seconds=ttl)
    key_id = S.RELIC_SIGNING_CURRENT_KEY_ID
    signed_headers = normalize_headers(
        {
            **headers,
            "host": host,
            "x-amz-content-sha256": UNSIGNED_PAYLOAD,
            USER_BINDING_HEADER: str(user_id),
        }
    )
    signed_header_names = ";".join(sorted(signed_headers))
    credential = f"{key_id}/{date_stamp}/{S.RELIC_SIGNING_REGION}/{SERVICE}/{TERMINATOR}"
    signed_query_params = {
        **(query_params or {}),
        "X-Amz-Algorithm": ALGORITHM,
        "X-Amz-Credential": credential,
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(ttl),
        "X-Amz-SignedHeaders": signed_header_names,
    }
    canonical_request = build_canonical_request(
        method=method,
        canonical_uri=canonical_uri,
        query_params=signed_query_params,
        headers=signed_headers,
        signed_header_names=signed_header_names,
    )
    signature = sign_string(
        secret=S.RELIC_SIGNING_KEYS[key_id],
        date_stamp=date_stamp,
        string_to_sign=build_string_to_sign(
            amz_date=amz_date,
            credential_scope=credential_scope(date_stamp),
            canonical_request=canonical_request,
        ),
    )
    signed_query_params["X-Amz-Signature"] = signature
    url = f"{canonical_uri}?{canonical_query_string(signed_query_params)}"
    response_headers = {
        name: value for name, value in signed_headers.items() if name != "host"
    }
    return SignedUrl(url=url, headers=response_headers, expires_at=expires_at)


def sign_put_url(
    *,
    bucket: str,
    key: str,
    headers: dict[str, str],
    user_id: uuid.UUID,
    host: str,
    ttl_seconds: int | None = None,
) -> SignedUrl:
    return sign_request_url(
        method="PUT",
        bucket=bucket,
        key=key,
        headers=headers,
        user_id=user_id,
        host=host,
        ttl_seconds=ttl_seconds,
    )


def sign_delete_url(
    *,
    bucket: str,
    key: str,
    user_id: uuid.UUID,
    host: str,
    ttl_seconds: int | None = None,
) -> SignedUrl:
    return sign_request_url(
        method="DELETE",
        bucket=bucket,
        key=key,
        headers={},
        user_id=user_id,
        host=host,
        ttl_seconds=ttl_seconds,
    )


def sign_get_url(
    *,
    bucket: str,
    key: str,
    user_id: uuid.UUID,
    host: str,
    ttl_seconds: int | None = None,
) -> SignedUrl:
    return sign_request_url(
        method="GET",
        bucket=bucket,
        key=key,
        headers={},
        user_id=user_id,
        host=host,
        ttl_seconds=ttl_seconds,
    )


def verify_signed_request(request: Request) -> VerifiedRequest:
    params = dict(request.query_params)
    required = [
        "X-Amz-Algorithm",
        "X-Amz-Credential",
        "X-Amz-Date",
        "X-Amz-Expires",
        "X-Amz-SignedHeaders",
        "X-Amz-Signature",
    ]
    if any(name not in params for name in required):
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "Missing SigV4 presigned URL parameters",
            status_code=400,
        )
    if params["X-Amz-Algorithm"] != ALGORITHM:
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "Unsupported signing algorithm",
            status_code=400,
        )

    key_id, date_stamp, region = parse_credential(params["X-Amz-Credential"])
    secret = S.RELIC_SIGNING_KEYS.get(key_id)
    if secret is None:
        raise S3SigningError("InvalidAccessKeyId", "Unknown signing key")
    if region != S.RELIC_SIGNING_REGION:
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "Credential region is invalid",
            status_code=400,
        )

    request_time = parse_amz_date(params["X-Amz-Date"])
    try:
        expires = int(params["X-Amz-Expires"])
    except ValueError as exc:
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "X-Amz-Expires must be an integer",
            status_code=400,
        ) from exc
    if expires < 1 or now_utc() > request_time + dt.timedelta(seconds=expires):
        raise S3SigningError("SignatureDoesNotMatch", "Presigned URL has expired")

    signed_header_names = params["X-Amz-SignedHeaders"]
    signed_headers = collect_signed_headers(request, signed_header_names)
    unsigned_params = {key: value for key, value in params.items() if key != "X-Amz-Signature"}
    canonical_request = build_canonical_request(
        method=request.method,
        canonical_uri=quote(request.url.path, safe="/~"),
        query_params=unsigned_params,
        headers=signed_headers,
        signed_header_names=signed_header_names,
    )
    expected = sign_string(
        secret=secret,
        date_stamp=date_stamp,
        string_to_sign=build_string_to_sign(
            amz_date=params["X-Amz-Date"],
            credential_scope=credential_scope(date_stamp, region=region),
            canonical_request=canonical_request,
        ),
    )
    if not hmac.compare_digest(expected, params["X-Amz-Signature"]):
        raise S3SigningError("SignatureDoesNotMatch", "The request signature is invalid")

    user_value = signed_headers.get(USER_BINDING_HEADER)
    if user_value is None:
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "Signed request is missing the user binding header",
            status_code=400,
        )
    try:
        user_id = uuid.UUID(user_value)
    except ValueError as exc:
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "Signed user binding is invalid",
            status_code=400,
        ) from exc
    return VerifiedRequest(user_id=user_id, key_id=key_id, signed_headers=signed_headers)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def parse_credential(credential: str) -> tuple[str, str, str]:
    parts = credential.split("/")
    if len(parts) != 5 or parts[3] != SERVICE or parts[4] != TERMINATOR:
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "Credential scope is invalid",
            status_code=400,
        )
    return parts[0], parts[1], parts[2]


def parse_amz_date(value: str) -> dt.datetime:
    try:
        return dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.UTC)
    except ValueError as exc:
        raise S3SigningError(
            "AuthorizationHeaderMalformed",
            "X-Amz-Date is invalid",
            status_code=400,
        ) from exc


def collect_signed_headers(request: Request, signed_header_names: str) -> dict[str, str]:
    names = signed_header_names.split(";")
    headers: dict[str, str] = {}
    for name in names:
        value = request.headers.get(name)
        if value is None:
            raise S3SigningError(
                "SignatureDoesNotMatch",
                f"Signed header {name} is missing",
            )
        headers[name] = value
    return normalize_headers(headers)


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name.lower(): normalize_header_value(value)
        for name, value in headers.items()
    }


def normalize_header_value(value: str) -> str:
    return " ".join(value.strip().split())


def canonical_object_uri(bucket: str, key: str) -> str:
    return f"/s3/{quote(bucket, safe='~')}/{quote(key, safe='/~')}"


def canonical_bucket_uri(bucket: str) -> str:
    return f"/s3/{quote(bucket, safe='~')}"


def build_canonical_request(
    *,
    method: str,
    canonical_uri: str,
    query_params: dict[str, str],
    headers: dict[str, str],
    signed_header_names: str,
) -> str:
    canonical_headers = "".join(
        f"{name}:{headers[name]}\n" for name in sorted(headers)
    )
    return "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_query_string(query_params),
            canonical_headers,
            signed_header_names,
            UNSIGNED_PAYLOAD,
        ]
    )


def canonical_query_string(params: dict[str, str]) -> str:
    return urlencode(sorted(params.items()), quote_via=quote, safe="-_.~")


def credential_scope(date_stamp: str, *, region: str | None = None) -> str:
    return f"{date_stamp}/{region or S.RELIC_SIGNING_REGION}/{SERVICE}/{TERMINATOR}"


def build_string_to_sign(
    *,
    amz_date: str,
    credential_scope: str,
    canonical_request: str,
) -> str:
    return "\n".join(
        [
            ALGORITHM,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )


def sign_string(
    *,
    secret: str,
    date_stamp: str,
    string_to_sign: str,
) -> str:
    signing_key = derive_signing_key(secret=secret, date_stamp=date_stamp)
    return hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()


def derive_signing_key(*, secret: str, date_stamp: str) -> bytes:
    date_key = hmac.new(f"AWS4{secret}".encode(), date_stamp.encode(), hashlib.sha256).digest()
    region_key = hmac.new(date_key, S.RELIC_SIGNING_REGION.encode(), hashlib.sha256).digest()
    service_key = hmac.new(region_key, SERVICE.encode(), hashlib.sha256).digest()
    return hmac.new(service_key, TERMINATOR.encode(), hashlib.sha256).digest()
