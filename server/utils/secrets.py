"""Redact sensitive credential values for API responses."""

MASKED_SECRET = "********"


def mask_access_key_id(key_id: str) -> str:
    """Return a stable, non-reversible identifier hint (last four characters)."""
    trimmed = key_id.strip()
    if len(trimmed) <= 4:
        return "****"
    return f"****{trimmed[-4:]}"


def mask_secret_access_key(_secret: str) -> str:
    """Never return decrypted secrets on read paths."""
    return MASKED_SECRET
