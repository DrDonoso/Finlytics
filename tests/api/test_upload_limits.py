"""Upload size cap: every endpoint that buffers a statement refuses one past the limit."""

from __future__ import annotations

import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from finlytics.api import uploads
from finlytics.api.uploads import max_base64_chars, read_upload

_LIMIT = 16


@pytest.fixture
def small_cap(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", _LIMIT)


def _upload(size: int, name: str = "statement.pdf") -> dict:
    return {"file": (name, b"x" * size, "application/octet-stream")}


# ── read_upload ──────────────────────────────────────────────────────────────

async def test_read_upload_accepts_a_file_exactly_at_the_limit(small_cap):
    data = b"x" * _LIMIT
    assert await read_upload(UploadFile(io.BytesIO(data), size=len(data))) == data


async def test_read_upload_rejects_a_declared_size_past_the_limit(small_cap):
    with pytest.raises(HTTPException) as exc:
        await read_upload(UploadFile(io.BytesIO(b""), size=_LIMIT + 1))
    assert exc.value.status_code == 413


async def test_read_upload_stops_reading_when_no_size_is_declared(small_cap, monkeypatch):
    monkeypatch.setattr(uploads, "_CHUNK_BYTES", 4)
    source = io.BytesIO(b"x" * 1000)

    with pytest.raises(HTTPException) as exc:
        await read_upload(UploadFile(source, size=None))

    assert exc.value.status_code == 413
    # It gives up on the chunk that crosses the cap instead of draining the stream.
    assert source.tell() <= _LIMIT + 4


@pytest.mark.parametrize("cap", [15, 16, 17])
def test_base64_cap_is_the_encoded_length_of_a_file_at_the_limit(monkeypatch, cap):
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", cap)
    assert max_base64_chars() == len(base64.b64encode(b"x" * cap))


def test_limit_message_names_the_cap_in_megabytes():
    assert "20 MB" in uploads.upload_too_large().detail


# ── Endpoints ────────────────────────────────────────────────────────────────

async def test_preview_rejects_an_oversized_statement(client_with_llm, small_cap):
    client, _ = client_with_llm
    with patch("finlytics.api.imports._parse_file", new_callable=AsyncMock) as parse:
        resp = await client.post("/api/imports/preview", files=_upload(_LIMIT + 1))

    assert resp.status_code == 413
    parse.assert_not_awaited()


async def test_one_shot_import_rejects_an_oversized_statement(client_with_llm, small_cap):
    client, _ = client_with_llm
    with patch("finlytics.api.imports._parse_file", new_callable=AsyncMock) as parse:
        resp = await client.post(
            "/api/imports", files=_upload(_LIMIT + 1), data={"account_name": "BBVA"}
        )

    assert resp.status_code == 413
    parse.assert_not_awaited()


@pytest.mark.parametrize("size", [_LIMIT + 1, _LIMIT * 4])
async def test_confirm_rejects_an_oversized_pdf_before_touching_the_database(
    client, mock_session, small_cap, size
):
    """Both guards: the encoded length, and the decoded size base64 padding hides."""
    payload = {
        "account_name": "BBVA",
        "source_filename": "statement.pdf",
        "transactions": [],
        "source_pdf_base64": base64.b64encode(b"x" * size).decode(),
    }

    resp = await client.post("/api/imports/confirm", json=payload)

    assert resp.status_code == 413
    mock_session.begin.assert_not_called()


@pytest.mark.parametrize("step", ["preview", "confirm"])
async def test_fidelity_import_rejects_an_oversized_csv(client, small_cap, step):
    with patch("finlytics.api.fidelity.parse_usd_open_lots_csv", MagicMock()) as parse:
        resp = await client.post(
            f"/api/investments/fidelity/import/{step}", files=_upload(_LIMIT + 1, "lots.csv")
        )

    assert resp.status_code == 413
    parse.assert_not_called()
