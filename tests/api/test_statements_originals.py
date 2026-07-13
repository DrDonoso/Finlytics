"""Tests for PDF-on-disk feature: confirm capture, originals listing, download.

Covers:
  - confirm with source_pdf_base64 writes file to disk + sets source_path
  - confirm without source_pdf_base64 leaves source_path NULL
  - slugify helper produces clean filenames
  - GET /api/statements/originals lists month's files (respects account_id)
  - GET /api/statements/original/{id} returns 200 + PDF bytes with attachment header
  - 404 when no run / no source_path / file missing on disk
"""

from __future__ import annotations

import base64
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.contracts import ExtractedTransaction
from finlytics.api.imports import _slugify


# ── _slugify unit tests ───────────────────────────────────────────────────────

def test_slugify_accent_removal():
    assert _slugify("Cuenta Nómina") == "Cuenta_Nomina"


def test_slugify_special_chars():
    assert _slugify("BBVA / ES") == "BBVA_ES"


def test_slugify_empty_fallback():
    assert _slugify("!!!") == "account"


def test_slugify_multiple_spaces():
    assert _slugify("  Foo   Bar  ") == "Foo_Bar"


def test_slugify_mixed_case_preserved():
    assert _slugify("MyBank") == "MyBank"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_extracted(year: int = 2026, month: int = 6) -> list[ExtractedTransaction]:
    return [
        ExtractedTransaction(
            transaction_date=date(year, month, 1),
            amount=Decimal("-10.00"),
            currency="EUR",
            description="SUPERMERCADO",
            category="Groceries",
            account_ref="TestAccount",
        )
    ]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ── confirm with PDF saves to disk ───────────────────────────────────────────

async def test_confirm_with_pdf_writes_file(client, mock_session, tmp_path):
    """confirm with source_pdf_base64 writes the PDF to disk and sets source_path."""
    pdf_bytes = b"%PDF-1.4 fake"
    b64_pdf = _b64(pdf_bytes)

    fake_account = MagicMock()
    fake_account.id = 1
    fake_account.name = "Cuenta Nomina"

    fake_run = MagicMock()
    fake_run.id = 10
    fake_run.source_path = None

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
        patch("finlytics.api.imports.settings.upload_dir", str(tmp_path)),
    ):
        payload = {
            "account_name": "Cuenta Nomina",
            "source_filename": "statement.pdf",
            "transactions": [
                {
                    "transaction_date": "2026-06-01",
                    "amount": "-10.00",
                    "currency": "EUR",
                    "description": "SUPERMERCADO",
                    "category": "Groceries",
                    "account_ref": "TestAccount",
                }
            ],
            "source_pdf_base64": b64_pdf,
        }
        resp = await client.post("/api/imports/confirm", json=payload)

    assert resp.status_code == 200
    expected_file = tmp_path / "Cuenta_Nomina_202606.pdf"
    assert expected_file.exists()
    assert expected_file.read_bytes() == pdf_bytes
    assert fake_run.source_path == "Cuenta_Nomina_202606.pdf"


async def test_confirm_without_pdf_leaves_source_path_none(client, mock_session, tmp_path):
    """confirm without source_pdf_base64 leaves source_path unset (None)."""
    fake_account = MagicMock()
    fake_account.id = 1
    fake_account.name = "BBVA"

    fake_run = MagicMock()
    fake_run.id = 11
    fake_run.source_path = None

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
        patch("finlytics.api.imports.settings.upload_dir", str(tmp_path)),
    ):
        payload = {
            "account_name": "BBVA",
            "source_filename": "statement.pdf",
            "transactions": [
                {
                    "transaction_date": "2026-06-01",
                    "amount": "-10.00",
                    "currency": "EUR",
                    "description": "SUPERMERCADO",
                    "category": "Groceries",
                    "account_ref": "BBVA",
                }
            ],
            # no source_pdf_base64
        }
        resp = await client.post("/api/imports/confirm", json=payload)

    assert resp.status_code == 200
    # No file should have been written
    assert list(tmp_path.iterdir()) == []
    assert fake_run.source_path is None


async def test_confirm_malformed_base64_skipped(client, mock_session, tmp_path):
    """Malformed base64 is silently ignored; import still succeeds."""
    fake_account = MagicMock()
    fake_account.id = 1
    fake_account.name = "BBVA"

    fake_run = MagicMock()
    fake_run.id = 12
    fake_run.source_path = None

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
        patch("finlytics.api.imports.settings.upload_dir", str(tmp_path)),
    ):
        payload = {
            "account_name": "BBVA",
            "source_filename": "statement.pdf",
            "transactions": [
                {
                    "transaction_date": "2026-06-01",
                    "amount": "-10.00",
                    "currency": "EUR",
                    "description": "SUPERMERCADO",
                    "category": "Groceries",
                    "account_ref": "BBVA",
                }
            ],
            "source_pdf_base64": "not-valid-base64!!!",
        }
        resp = await client.post("/api/imports/confirm", json=payload)

    assert resp.status_code == 200
    # Malformed base64 → no file, source_path stays None
    assert list(tmp_path.iterdir()) == []


async def test_confirm_file_write_failure_import_still_succeeds(client, mock_session, tmp_path):
    """If the file write raises, the import still completes without source_path."""
    pdf_bytes = b"%PDF fake"

    fake_account = MagicMock()
    fake_account.id = 1
    fake_account.name = "BBVA"

    fake_run = MagicMock()
    fake_run.id = 13
    fake_run.source_path = None

    import builtins
    real_open = builtins.open

    def _failing_open(path, mode="r", **kwargs):
        if "wb" in mode:
            raise OSError("disk full")
        return real_open(path, mode, **kwargs)

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
        patch("finlytics.api.imports.settings.upload_dir", str(tmp_path)),
        patch("builtins.open", side_effect=_failing_open),
    ):
        payload = {
            "account_name": "BBVA",
            "source_filename": "statement.pdf",
            "transactions": [
                {
                    "transaction_date": "2026-06-01",
                    "amount": "-10.00",
                    "currency": "EUR",
                    "description": "SUPERMERCADO",
                    "category": "Groceries",
                    "account_ref": "BBVA",
                }
            ],
            "source_pdf_base64": _b64(pdf_bytes),
        }
        resp = await client.post("/api/imports/confirm", json=payload)

    assert resp.status_code == 200
    assert fake_run.source_path is None


# ── GET /api/statements/originals ────────────────────────────────────────────

_NOW = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

_ORIGINALS = [
    {
        "import_run_id": 5,
        "source_filename": "BBVA_202606.pdf",
        "account_name": "BBVA",
        "imported_at": _NOW,
    }
]


async def test_list_originals_status_200(client):
    with patch("finlytics.db.queries.get_statement_originals", new_callable=AsyncMock) as mock:
        mock.return_value = _ORIGINALS
        resp = await client.get("/api/statements/originals?year=2026&month=6")

    assert resp.status_code == 200


async def test_list_originals_returns_entries(client):
    with patch("finlytics.db.queries.get_statement_originals", new_callable=AsyncMock) as mock:
        mock.return_value = _ORIGINALS
        resp = await client.get("/api/statements/originals?year=2026&month=6")

    assert len(resp.json()) == 1


async def test_list_originals_schema_fields(client):
    with patch("finlytics.db.queries.get_statement_originals", new_callable=AsyncMock) as mock:
        mock.return_value = [_ORIGINALS[0]]
        resp = await client.get("/api/statements/originals?year=2026&month=6")

    item = resp.json()[0]
    assert set(item.keys()) == {"import_run_id", "source_filename", "account_name", "imported_at"}
    assert item["import_run_id"] == 5
    assert item["source_filename"] == "BBVA_202606.pdf"
    assert item["account_name"] == "BBVA"


async def test_list_originals_account_id_forwarded(client):
    with patch("finlytics.db.queries.get_statement_originals", new_callable=AsyncMock) as mock:
        mock.return_value = _ORIGINALS
        await client.get("/api/statements/originals?year=2026&month=6&account_id=3")

    _, kwargs = mock.call_args
    assert kwargs["account_id"] == 3


async def test_list_originals_no_account_id_passes_none(client):
    with patch("finlytics.db.queries.get_statement_originals", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/statements/originals?year=2026&month=6")

    _, kwargs = mock.call_args
    assert kwargs["account_id"] is None


async def test_list_originals_year_month_forwarded(client):
    with patch("finlytics.db.queries.get_statement_originals", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/statements/originals?year=2025&month=3")

    _, kwargs = mock.call_args
    assert kwargs["year"] == 2025
    assert kwargs["month"] == 3


async def test_list_originals_empty(client):
    with patch("finlytics.db.queries.get_statement_originals", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/statements/originals?year=2026&month=6")

    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /api/statements/original/{id} ────────────────────────────────────────

async def test_download_original_returns_pdf(client, mock_session, tmp_path):
    """Endpoint returns PDF bytes when run and file exist."""
    pdf_bytes = b"%PDF-1.4 real content"
    pdf_path = tmp_path / "BBVA_202606.pdf"
    pdf_path.write_bytes(pdf_bytes)

    fake_run = MagicMock()
    fake_run.id = 7
    fake_run.source_path = "BBVA_202606.pdf"

    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_run))
    )

    with patch("finlytics.api.statements.settings.upload_dir", str(tmp_path)):
        resp = await client.get("/api/statements/original/7")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == pdf_bytes


async def test_download_original_404_run_missing(client, mock_session):
    """404 when the ImportRun does not exist."""
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    resp = await client.get("/api/statements/original/999")
    assert resp.status_code == 404


async def test_download_original_404_no_source_path(client, mock_session):
    """404 when the run exists but has no source_path."""
    fake_run = MagicMock()
    fake_run.id = 8
    fake_run.source_path = None

    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_run))
    )
    resp = await client.get("/api/statements/original/8")
    assert resp.status_code == 404


async def test_download_original_404_file_missing_on_disk(client, mock_session, tmp_path):
    """404 when source_path is set but the file is not on disk."""
    fake_run = MagicMock()
    fake_run.id = 9
    fake_run.source_path = "BBVA_202606.pdf"

    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_run))
    )

    with patch("finlytics.api.statements.settings.upload_dir", str(tmp_path)):
        resp = await client.get("/api/statements/original/9")

    assert resp.status_code == 404
