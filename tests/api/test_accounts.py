"""Tests for GET /api/accounts and DELETE /api/accounts/{id}."""

from unittest.mock import AsyncMock, patch

import pytest


_ACCOUNT_ROW = {"id": 1, "name": "BBVA", "type": "bank", "currency": "EUR", "tx_count": 5}
_ACCOUNT_ROW2 = {"id": 2, "name": "Indexa Capital", "type": "broker", "currency": "EUR", "tx_count": 0}


# ── GET /api/accounts ─────────────────────────────────────────────────────────

async def test_list_accounts_returns_list(client):
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [_ACCOUNT_ROW, _ACCOUNT_ROW2]
        resp = await client.get("/api/accounts")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "BBVA"
    assert data[1]["name"] == "Indexa Capital"


async def test_list_accounts_empty(client):
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/accounts")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_account_schema_fields(client):
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [_ACCOUNT_ROW]
        resp = await client.get("/api/accounts")

    item = resp.json()[0]
    assert set(item.keys()) == {"id", "name", "type", "currency", "tx_count"}
    assert isinstance(item["id"], int)
    assert isinstance(item["name"], str)
    assert isinstance(item["tx_count"], int)


async def test_account_type_nullable(client):
    """type field may be null per API contract."""
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [{"id": 1, "name": "Test", "type": None, "currency": "EUR", "tx_count": 0}]
        resp = await client.get("/api/accounts")

    assert resp.status_code == 200
    assert resp.json()[0]["type"] is None


async def test_account_tx_count_present(client):
    """tx_count is returned for each account."""
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [_ACCOUNT_ROW]
        resp = await client.get("/api/accounts")

    assert resp.json()[0]["tx_count"] == 5


async def test_account_tx_count_zero_for_empty_account(client):
    """Accounts with no transactions report tx_count=0 (not absent)."""
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [_ACCOUNT_ROW2]
        resp = await client.get("/api/accounts")

    item = resp.json()[0]
    assert item["tx_count"] == 0


async def test_account_existing_fields_unchanged(client):
    """id, name, type, currency are still present alongside tx_count."""
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [_ACCOUNT_ROW]
        resp = await client.get("/api/accounts")

    item = resp.json()[0]
    assert item["id"] == 1
    assert item["name"] == "BBVA"
    assert item["type"] == "bank"
    assert item["currency"] == "EUR"


# ── DELETE /api/accounts/{account_id} ────────────────────────────────────────

async def test_delete_account_status_200(client):
    with patch("finlytics.db.queries.delete_account", new_callable=AsyncMock) as mock:
        mock.return_value = 12
        resp = await client.delete("/api/accounts/1")

    assert resp.status_code == 200


async def test_delete_account_returns_deleted_count(client):
    with patch("finlytics.db.queries.delete_account", new_callable=AsyncMock) as mock:
        mock.return_value = 12
        resp = await client.delete("/api/accounts/1")

    assert resp.json() == {"deleted": 12}


async def test_delete_account_zero_transactions(client):
    """Account with no transactions returns {deleted: 0} — not an error."""
    with patch("finlytics.db.queries.delete_account", new_callable=AsyncMock) as mock:
        mock.return_value = 0
        resp = await client.delete("/api/accounts/2")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0}


async def test_delete_account_not_found_returns_404(client):
    with patch("finlytics.db.queries.delete_account", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = await client.delete("/api/accounts/99")

    assert resp.status_code == 404


async def test_delete_account_passes_account_id(client):
    """Router forwards the path parameter to the query function."""
    with patch("finlytics.db.queries.delete_account", new_callable=AsyncMock) as mock:
        mock.return_value = 3
        await client.delete("/api/accounts/7")

    mock.assert_called_once()
    args, _ = mock.call_args
    assert args[1] == 7
