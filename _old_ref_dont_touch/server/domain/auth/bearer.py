"""Parse control-plane Bearer tokens (access key id + secret)."""


def parse_bearer_access_key(authorization: str | None) -> tuple[str, str] | None:
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    key_id, separator, secret = token.partition(":")
    if not separator or not key_id or not secret:
        return None

    return key_id, secret
