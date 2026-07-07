"""Tests for GET /api/accounts."""

from unittest.mock import AsyncMock, patch

import pytest


_ACCOUNT_ROW = {"id": 1, "name": "BBVA", "type": "bank", "currency": "EUR"}
_ACCOUNT_ROW2 = {"id": 2, "name": "Indexa Capital", "type": "broker", "currency": "EUR"}


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
    assert set(item.keys()) == {"id", "name", "type", "currency"}
    assert isinstance(item["id"], int)
    assert isinstance(item["name"], str)


async def test_account_type_nullable(client):
    """type field may be null per API contract."""
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [{"id": 1, "name": "Test", "type": None, "currency": "EUR"}]
        resp = await client.get("/api/accounts")

    assert resp.status_code == 200
    assert resp.json()[0]["type"] is None
