"""Streaming helpers for object storage adapters."""

from typing import BinaryIO


class RangeLimitedReader:
    """Wrap a readable stream, returning at most ``max_bytes`` then stopping."""

    def __init__(self, body: BinaryIO, max_bytes: int) -> None:
        self._body = body
        self._remaining = max_bytes

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size < 0 or size > self._remaining:
            size = self._remaining
        chunk = self._body.read(size)
        self._remaining -= len(chunk)
        return chunk

    def close(self) -> None:
        self._body.close()

    def __enter__(self) -> "RangeLimitedReader":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
