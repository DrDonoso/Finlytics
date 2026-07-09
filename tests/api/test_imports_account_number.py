"""Tests for account-number detection in POST /api/imports/preview and /confirm."""

from __future__ import annotations

import io
from decimal import Decimal
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.contracts import ExtractedTransaction


_IBAN = "ES7921000813610123456789"

# Masked form: "ES" + 18 stars + last 4
_IBAN_MASKED = "ES" + "*" * (len(_IBAN) - 6) + _IBAN[-4:]


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


# ── Preview: IBAN detection ───────────────────────────────────────────────────

async def test_preview_iban_matched_returns_detection_fields(client_with_llm, mock_session):
    """When IBAN found in header and matches a DB account → all detection fields populated."""
    client, _ = client_with_llm
    extracted = _make_extracted()

    fake_account = MagicMock()
    fake_account.id = 5
    fake_account.name = "BBVA"

    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = fake_account
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    with (
        patch("finlytics.api.imports.parse_statement", return_value="header text"),
        patch("finlytics.api.imports.extract_account_number", return_value=_IBAN),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_account_iban"] == _IBAN
    assert body["detected_account_masked"] == _IBAN_MASKED
    assert body["matched_account_id"] == 5
    assert body["matched_account_name"] == "BBVA"
    # account_ref in preview uses the matched account's name
    assert body["account_ref"] == "BBVA"


async def test_preview_iban_matched_uses_account_name_as_ref(client_with_llm, mock_session):
    """When IBAN matches, extraction uses matched account name (not supplied account_name)."""
    client, _ = client_with_llm

    fake_account = MagicMock()
    fake_account.id = 3
    fake_account.name = "Caixa"

    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = fake_account
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    mock_extract = AsyncMock(return_value=_make_extracted())
    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_account_number", return_value=_IBAN),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "WRONG NAME"},  # should be overridden by matched name
        )

    assert resp.status_code == 200
    # The extraction was called with the matched account name
    assert mock_extract.call_args[0][1] == "Caixa"


async def test_preview_iban_detected_no_match(client_with_llm, mock_session):
    """IBAN detected in statement but no DB account exists → partial detection fields."""
    client, _ = client_with_llm
    extracted = _make_extracted()

    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = None  # not found
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_account_number", return_value=_IBAN),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_account_iban"] == _IBAN
    assert body["detected_account_masked"] == _IBAN_MASKED
    assert body["matched_account_id"] is None
    assert body["matched_account_name"] is None


async def test_preview_no_iban_detected(client_with_llm, mock_session):
    """No IBAN in statement → all detection fields are None."""
    client, _ = client_with_llm
    extracted = _make_extracted()

    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_account_number", return_value=None),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_account_iban"] is None
    assert body["detected_account_masked"] is None
    assert body["matched_account_id"] is None
    assert body["matched_account_name"] is None


async def test_preview_new_iban_no_name_does_not_crash(client_with_llm, mock_session):
    """New IBAN (no match) with no account_name — extraction uses empty ref, no crash."""
    client, _ = client_with_llm
    extracted = _make_extracted()

    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    with (
        patch("finlytics.api.imports.parse_statement", return_value="text"),
        patch("finlytics.api.imports.extract_account_number", return_value=_IBAN),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=extracted),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[]),
    ):
        # Neither account_name nor a matched account — should still return 200
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
        )

    assert resp.status_code == 200


# ── Confirm: account_number resolution ───────────────────────────────────────

async def test_confirm_with_account_number_existing(client, mock_session):
    """account_number provided + matches DB → uses existing account (name ignored)."""
    fake_account = MagicMock()
    fake_account.id = 7
    fake_account.name = "BBVA"

    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = fake_account
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    fake_run = MagicMock()
    fake_run.id = 99

    with (
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": "IGNORED NAME",
                "account_number": _IBAN,
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


async def test_confirm_with_account_number_new_creates_account(client, mock_session):
    """account_number provided + not found → new Account created with name + number."""
    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = None  # not found
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    fake_run = MagicMock()
    fake_run.id = 77

    created_accounts = []

    def _capture_add(obj):
        created_accounts.append(obj)

    mock_session.add = MagicMock(side_effect=_capture_add)

    with (
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": "Mi BBVA",
                "account_number": _IBAN,
                "source_filename": "bank.pdf",
                "transactions": [
                    {
                        "transaction_date": "2024-06-01",
                        "amount": -42.5,
                        "currency": "EUR",
                        "description": "MERCADONA",
                        "category": "Groceries",
                        "account_ref": "Mi BBVA",
                    }
                ],
            },
        )

    assert resp.status_code == 200
    # A new Account was session.add()'d
    from finlytics.db.models import Account
    new_accounts = [a for a in created_accounts if isinstance(a, Account)]
    assert len(new_accounts) == 1
    assert new_accounts[0].account_number == _IBAN
    assert new_accounts[0].name == "Mi BBVA"


async def test_confirm_with_account_number_new_no_name_returns_422(client, mock_session):
    """account_number new + no account_name → 422."""
    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    resp = await client.post(
        "/api/imports/confirm",
        json={
            "account_number": _IBAN,
            "source_filename": "bank.pdf",
            "transactions": [],
        },
    )

    assert resp.status_code == 422


async def test_confirm_without_account_number_falls_back_to_name(client):
    """No account_number → resolves by account_name (legacy path)."""
    fake_account = MagicMock()
    fake_account.id = 5
    fake_account.name = "BBVA"

    fake_run = MagicMock()
    fake_run.id = 55

    with (
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account) as mock_resolve,
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
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
    mock_resolve.assert_called_once()


async def test_confirm_dedup_account_ref_unchanged(client, mock_session):
    """account_ref in transactions is NOT replaced with the IBAN — dedup stays by name."""
    mock_iban_result = MagicMock()
    mock_iban_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_iban_result)

    fake_run = MagicMock()
    fake_run.id = 11

    captured_txs: list = []

    async def _capture_upsert(session, import_run, txs, *, tag_colors=None):
        captured_txs.extend(txs)
        return (len(txs), 0)

    mock_session.add = MagicMock()

    with (
        patch("finlytics.api.imports.ImportRun", return_value=fake_run),
        patch("finlytics.api.imports.upsert_transactions", side_effect=_capture_upsert),
    ):
        await client.post(
            "/api/imports/confirm",
            json={
                "account_name": "BBVA",
                "account_number": _IBAN,
                "source_filename": "bank.pdf",
                "transactions": [
                    {
                        "transaction_date": "2024-06-01",
                        "amount": -42.5,
                        "currency": "EUR",
                        "description": "MERCADONA",
                        "category": "Groceries",
                        "account_ref": "BBVA",  # name, NOT the IBAN
                    }
                ],
            },
        )

    # account_ref must still be "BBVA" (name), not the IBAN
    assert len(captured_txs) == 1
    assert captured_txs[0].account_ref == "BBVA"
    assert captured_txs[0].account_ref != _IBAN


async def test_confirm_no_account_number_no_account_name_returns_422(client):
    """Neither account_number nor account_name → 422."""
    resp = await client.post(
        "/api/imports/confirm",
        json={
            "source_filename": "bank.pdf",
            "transactions": [],
        },
    )
    assert resp.status_code == 422
