"""Pure filename validation and normalization for control-plane file ops."""

import os

from domain.exceptions import BadRequestError


def validate_filename(name: str) -> None:
    if not name or not name.strip():
        raise BadRequestError("Filename cannot be empty")
    if "/" in name:
        raise BadRequestError("Filename cannot contain '/'")
    if len(name) > 255:
        raise BadRequestError("Filename is too long")


def with_preserved_extension(original_filename: str, new_filename: str) -> str:
    """If *new_filename* has no extension, append *original_filename*'s extension."""
    _, old_ext = os.path.splitext(original_filename)
    _, new_ext = os.path.splitext(new_filename)
    if new_ext or not old_ext:
        return new_filename
    return f"{new_filename}{old_ext}"


def normalize_requested_file_name(*, current_name: str, requested_name: str) -> str:
    name = requested_name.strip()
    validate_filename(name)
    name = with_preserved_extension(current_name, name)
    validate_filename(name)
    return name
