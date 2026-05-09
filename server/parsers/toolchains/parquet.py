"""Parquet parser. Writes compact discovery metadata into file meta.

No configuration. Always extracts the same set of fields, with fallbacks
to capture data from quirky/non-standard parquet variants where possible.
"""

from __future__ import annotations

from typing import Any


def parse_parquet(*, prefix: bytes = b"") -> dict[str, Any]:
    del prefix
    raise NotImplementedError("Parquet parser toolchain is not implemented yet")
