"""Bounded reads of uploaded statements.

``UploadFile.read()`` with no argument loads the whole part into memory, so one
oversized request is enough to exhaust the container.  A statement is a few
megabytes at most; anything past the cap is refused with 413 before it is
buffered.

This bounds what the application holds in memory, not the request itself:
Starlette spools a multipart body to a temporary file before the endpoint runs.
Capping the body on the wire belongs to the reverse proxy.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

__all__ = [
    "MAX_UPLOAD_BYTES",
    "ensure_within_limit",
    "max_base64_chars",
    "read_upload",
    "upload_too_large",
]

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_CHUNK_BYTES = 1024 * 1024


def upload_too_large() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.",
    )


def ensure_within_limit(size: int) -> None:
    if size > MAX_UPLOAD_BYTES:
        raise upload_too_large()


def max_base64_chars() -> int:
    """Longest base64 text that a file within ``MAX_UPLOAD_BYTES`` encodes to.

    Padding makes this up to two bytes lenient, so check the decoded size too.
    """
    return 4 * -(-MAX_UPLOAD_BYTES // 3)


async def read_upload(file: UploadFile) -> bytes:
    """Read ``file`` into memory, raising 413 as soon as it exceeds the cap."""
    if file.size is not None:
        ensure_within_limit(file.size)

    buffer = bytearray()
    while chunk := await file.read(_CHUNK_BYTES):
        buffer += chunk
        ensure_within_limit(len(buffer))
    return bytes(buffer)
