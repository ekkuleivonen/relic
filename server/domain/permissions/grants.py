"""Folder access grant validation."""

from constants import FOLDER_ACCESS_PERMISSION_MASK
from domain.exceptions import BadRequestError
from enums import Permission


def validate_folder_permissions(permissions: int) -> None:
    if permissions <= 0:
        raise BadRequestError("Permissions must include at least one capability")

    if permissions & ~int(FOLDER_ACCESS_PERMISSION_MASK):
        raise BadRequestError("Permissions contain unknown bits")

    has_read = bool(permissions & int(Permission.READ))
    needs_read = bool(
        permissions & int(Permission.WRITE | Permission.DELETE | Permission.ENRICH)
    )
    if needs_read and not has_read:
        raise BadRequestError("Write, delete, and enrich grants require read access")
