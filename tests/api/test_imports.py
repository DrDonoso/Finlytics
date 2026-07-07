"""Tests for POST /api/imports (one-shot), /preview and /confirm."""

from __future__ import annotations

import io
from decimal import Decimal
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from finlytics.contracts import ExtractedTransaction


def _make_extracted() -> list[ExtractedTransaction]:
    return [
        ExtractedTransaction(
            transaction_date=date(2024, 6, 1),
            amount=Decimal("-42.50"),
            currency="EUR",
            description="MERCADONA",
            category="Groceries",
            account_ref="BBVA",
        )
    ]


# ── One-shot POST /api/imports ────────────────────────────────────────────────

async def test_import_success(client_with_llm):
    client, mock_llm = client_with_llm
    extracted = _make_extracted()

    fake_account = MagicMock()
    fake_account.id = 1
    fake_account.name = "BBVA"

    fake_import_run = MagicMock()
    fake_import_run.id = 42

    with (
        patch("finlytics.api.imports.parse_statement", return_value="parsed text"),
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=fake_import_run),
    ):
        resp = await client.post(
            "/api/imports",
            files={"file": ("statement.pdf", io.BytesIO(b"fake pdf"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["import_run_id"] == 42
    assert body["num_parsed"] == 1
    assert body["num_inserted"] == 1
    assert body["num_duplicates"] == 0


async def test_import_missing_account_params(client_with_llm):
    """Both account_name and account_id missing → 422."""
    client, _ = client_with_llm
    resp = await client.post(
        "/api/imports",
        files={"file": ("statement.pdf", io.BytesIO(b"fake"), "application/pdf")},
        # No account_name or account_id
    )
    assert resp.status_code == 422


async def test_import_llm_not_configured(client_no_llm):
    """When LLM is not configured get_llm_client raises 503.

    Uses client_no_llm fixture which explicitly overrides get_llm_client to
    raise 503 — this makes the test env-independent (works whether or not
    OPENAI_* vars happen to be set in the local .env).
    """
    resp = await client_no_llm.post(
        "/api/imports",
        files={"file": ("statement.pdf", io.BytesIO(b"fake"), "application/pdf")},
        data={"account_name": "BBVA"},
    )
    assert resp.status_code == 503


async def test_import_unknown_account_id(client_with_llm):
    """_resolve_account raises 404 when account_id not found."""
    client, _ = client_with_llm
    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              side_effect=HTTPException(status_code=404, detail="Account 99 not found")),
    ):
        resp = await client.post(
            "/api/imports",
            files={"file": ("statement.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_id": "99"},
        )

    assert resp.status_code == 404


async def test_import_unsupported_file_type(client_with_llm):
    """Uploading an unsupported file extension returns 422."""
    client, _ = client_with_llm
    with patch("finlytics.api.imports.parse_statement",
               side_effect=ValueError("Unsupported file type: 'docx'")):
        resp = await client.post(
            "/api/imports",
            files={"file": ("report.docx", io.BytesIO(b"fake"), "application/octet-stream")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 422


# ── POST /api/imports/preview ─────────────────────────────────────────────────

async def test_preview_returns_transactions(client_with_llm):
    """Preview returns PreviewOut with transactions and does NOT persist anything."""
    client, _ = client_with_llm
    extracted = _make_extracted()

    with (
        patch("finlytics.api.imports.parse_statement", return_value="statement text"),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["account_ref"] == "BBVA"
    assert body["filename"] == "bank.pdf"
    assert len(body["transactions"]) == 1
    tx = body["transactions"][0]
    assert tx["description"] == "MERCADONA"
    assert tx["category"] == "Groceries"
    assert isinstance(tx["amount"], float)  # Decimal serialised as JSON number
    assert tx["amount"] < 0


async def test_preview_does_not_persist(client_with_llm, mock_session):
    """Preview must NOT touch the DB (no session.add, no session.begin)."""
    client, _ = client_with_llm

    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=_make_extracted()),
    ):
        await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
        )

    mock_session.add.assert_not_called()
    mock_session.begin.assert_not_called()


async def test_preview_no_llm_returns_503(client_no_llm):
    """LLM client not configured → 503 before any parsing occurs."""
    resp = await client_no_llm.post(
        "/api/imports/preview",
        files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
    )
    assert resp.status_code == 503


async def test_preview_parse_error_returns_400(client_with_llm):
    """Unparseable file → 400 (not 422) on the preview endpoint."""
    client, _ = client_with_llm
    with patch("finlytics.api.imports.parse_statement",
               side_effect=ValueError("not a valid PDF")):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bad.pdf", io.BytesIO(b"garbage"), "application/pdf")},
        )
    assert resp.status_code == 400


async def test_preview_year_detected(client_with_llm):
    """detect_statement_year finds a year → year_detected True, statement_year populated."""
    client, _ = client_with_llm
    extracted = _make_extracted()

    with (
        patch("finlytics.api.imports.parse_statement", return_value="statement text"),
        patch("finlytics.api.imports.detect_statement_year", return_value=2026),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["year_detected"] is True
    assert body["statement_year"] == 2026


async def test_preview_year_not_detected(client_with_llm):
    """detect_statement_year returns None → year_detected False, statement_year null."""
    client, _ = client_with_llm
    extracted = _make_extracted()

    with (
        patch("finlytics.api.imports.parse_statement", return_value="statement text"),
        patch("finlytics.api.imports.detect_statement_year", return_value=None),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["year_detected"] is False
    assert body["statement_year"] is None


# ── POST /api/imports/confirm ─────────────────────────────────────────────────

async def test_confirm_success(client):
    """Confirm endpoint persists submitted transactions and returns ImportResult."""
    fake_account = MagicMock()
    fake_account.id = 5
    fake_account.name = "BBVA"

    fake_import_run = MagicMock()
    fake_import_run.id = 99

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.ImportRun", return_value=fake_import_run),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": "BBVA",
                "source_filename": "bank.pdf",
                "transactions": [
                    {
                        "transaction_date": "2024-06-01",
                        "amount": -42.5,
                        "currency": "EUR",
                        "description": "MERCADONA",
                        "category": "Groceries",
                        "account_ref": "BBVA",
                    }
                ],
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["import_run_id"] == 99
    assert body["num_parsed"] == 1
    assert body["num_inserted"] == 1
    assert body["num_duplicates"] == 0


async def test_confirm_upsert_receives_submitted_transactions(client):
    """upsert_transactions must receive the exact (possibly edited) transaction list."""
    fake_account = MagicMock()
    fake_account.id = 3
    fake_import_run = MagicMock()
    fake_import_run.id = 7

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.ImportRun", return_value=fake_import_run),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(2, 1)) as mock_upsert,
    ):
        await client.post(
            "/api/imports/confirm",
            json={
                "account_name": "BBVA",
                "source_filename": "stmt.csv",
                "transactions": [
                    {
                        "transaction_date": "2024-06-01",
                        "amount": -10.0,
                        "description": "EDITED DESCRIPTION",
                        "category": "My Custom Category",
                        "account_ref": "BBVA",
                    },
                    {
                        "transaction_date": "2024-06-02",
                        "amount": -20.0,
                        "description": "LIDL",
                        "category": "Groceries",
                        "account_ref": "BBVA",
                    },
                ],
            },
        )

    assert mock_upsert.called
    passed_txs = mock_upsert.call_args[0][2]  # third positional arg: list[ExtractedTransaction]
    assert len(passed_txs) == 2
    assert passed_txs[0].category == "My Custom Category"
    assert passed_txs[1].description == "LIDL"


# ── Preview: suggested_tags ───────────────────────────────────────────────────

async def test_preview_suggested_tags_for_new_tags(client_with_llm, mock_session):
    """Preview returns suggested_tags (name+color) for tags not yet in the DB."""
    client, _ = client_with_llm
    extracted = [
        ExtractedTransaction(
            transaction_date=date(2024, 6, 1),
            amount=Decimal("-42.50"),
            currency="EUR",
            description="MERCADONA",
            category="Groceries",
            account_ref="BBVA",
            tags=["agua", "luz"],
        )
    ]
    # DB returns no existing tags → both "agua" and "luz" are new
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_db_result)

    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.suggest_tag_colors", new_callable=AsyncMock,
              return_value={"agua": "#3b82f6", "luz": "#eab308"}),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "suggested_tags" in body
    color_by_name = {t["name"]: t["color"] for t in body["suggested_tags"]}
    assert color_by_name["agua"] == "#3b82f6"
    assert color_by_name["luz"] == "#eab308"


async def test_preview_suggested_tags_empty_when_all_existing(client_with_llm, mock_session):
    """Preview omits suggested_tags (empty list) when every tag is already in the DB."""
    client, _ = client_with_llm
    extracted = [
        ExtractedTransaction(
            transaction_date=date(2024, 6, 1),
            amount=Decimal("-10.00"),
            currency="EUR",
            description="ENDESA",
            category="Utilities",
            account_ref="BBVA",
            tags=["luz"],
        )
    ]
    # DB already has "luz"
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = ["luz"]
    mock_session.execute = AsyncMock(return_value=mock_db_result)

    suggest_mock = AsyncMock(return_value={"luz": "#eab308"})
    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.suggest_tag_colors", suggest_mock),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    assert resp.json()["suggested_tags"] == []
    suggest_mock.assert_not_called()


async def test_preview_suggested_tags_none_on_helper_failure(client_with_llm, mock_session):
    """suggest_tag_colors returning None → suggested_tags falls back to []."""
    client, _ = client_with_llm
    extracted = [
        ExtractedTransaction(
            transaction_date=date(2024, 6, 1),
            amount=Decimal("-5.00"),
            currency="EUR",
            description="AQUALIA",
            category="Utilities",
            account_ref="BBVA",
            tags=["agua"],
        )
    ]
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_db_result)

    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.suggest_tag_colors", new_callable=AsyncMock,
              return_value=None),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    assert resp.json()["suggested_tags"] == []


# ── Confirm: tag_colors threading ─────────────────────────────────────────────

async def test_confirm_tag_colors_passed_to_upsert(client):
    """tag_colors in ConfirmIn is forwarded to upsert_transactions."""
    fake_account = MagicMock()
    fake_account.id = 5
    fake_import_run = MagicMock()
    fake_import_run.id = 99

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.ImportRun", return_value=fake_import_run),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)) as mock_upsert,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": "BBVA",
                "source_filename": "bank.pdf",
                "transactions": [
                    {
                        "transaction_date": "2024-06-01",
                        "amount": -42.5,
                        "currency": "EUR",
                        "description": "MERCADONA",
                        "category": "Groceries",
                        "account_ref": "BBVA",
                        "tags": ["agua"],
                    }
                ],
                "tag_colors": {"agua": "#3b82f6"},
            },
        )

    assert resp.status_code == 200
    assert mock_upsert.call_args.kwargs.get("tag_colors") == {"agua": "#3b82f6"}


async def test_confirm_tag_colors_none_when_omitted(client):
    """Omitting tag_colors from ConfirmIn passes None to upsert_transactions."""
    fake_account = MagicMock()
    fake_account.id = 5
    fake_import_run = MagicMock()
    fake_import_run.id = 99

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.ImportRun", return_value=fake_import_run),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)) as mock_upsert,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": "BBVA",
                "source_filename": "bank.pdf",
                "transactions": [
                    {
                        "transaction_date": "2024-06-01",
                        "amount": -42.5,
                        "currency": "EUR",
                        "description": "MERCADONA",
                        "category": "Groceries",
                        "account_ref": "BBVA",
                    }
                ],
                # tag_colors intentionally omitted
            },
        )

    assert resp.status_code == 200
    assert mock_upsert.call_args.kwargs.get("tag_colors") is None


# ── get_or_create_tag: color-on-create only ───────────────────────────────────

async def test_get_or_create_tag_applies_color_on_creation():
    """get_or_create_tag creates a new tag with the supplied color."""
    from finlytics.db.repository import get_or_create_tag
    from finlytics.db.models import Tag

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # tag does not exist

    mock_sess = MagicMock()
    mock_sess.execute = AsyncMock(return_value=mock_result)
    mock_sess.flush = AsyncMock()
    mock_sess.add = MagicMock()

    tag = await get_or_create_tag(mock_sess, "agua", color="#3b82f6")

    assert tag.name == "agua"
    assert tag.color == "#3b82f6"
    mock_sess.add.assert_called_once_with(tag)


async def test_get_or_create_tag_does_not_recolor_existing():
    """get_or_create_tag never overwrites an existing tag's color."""
    from finlytics.db.repository import get_or_create_tag
    from finlytics.db.models import Tag

    existing = Tag(id=7, name="agua", color="#aabbcc")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing

    mock_sess = MagicMock()
    mock_sess.execute = AsyncMock(return_value=mock_result)
    mock_sess.add = MagicMock()

    returned = await get_or_create_tag(mock_sess, "agua", color="#3b82f6")

    assert returned is existing
    assert returned.color == "#aabbcc"   # unchanged
    mock_sess.add.assert_not_called()
