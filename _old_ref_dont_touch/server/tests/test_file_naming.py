import pytest

from domain.exceptions import BadRequestError
from domain.files.naming import (
    normalize_requested_file_name,
    validate_filename,
    with_preserved_extension,
)


def test_validate_filename_rejects_empty() -> None:
    with pytest.raises(BadRequestError, match="empty"):
        validate_filename("")


def test_validate_filename_rejects_slash() -> None:
    with pytest.raises(BadRequestError, match="/"):
        validate_filename("a/b")


def test_validate_filename_rejects_too_long() -> None:
    with pytest.raises(BadRequestError, match="too long"):
        validate_filename("x" * 256)


def test_with_preserved_extension_appends_when_missing() -> None:
    assert with_preserved_extension("photo.jpg", "renamed") == "renamed.jpg"


def test_with_preserved_extension_keeps_explicit_extension() -> None:
    assert with_preserved_extension("photo.jpg", "renamed.png") == "renamed.png"


def test_normalize_requested_file_name_trims_and_preserves_extension() -> None:
    assert (
        normalize_requested_file_name(
            current_name="report.pdf", requested_name="  final  "
        )
        == "final.pdf"
    )
