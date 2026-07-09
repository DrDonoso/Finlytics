"""Tests for GET /api/accounts, PATCH /api/accounts/{id}, and DELETE /api/accounts/{id}."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.api.schemas import mask_account_number


_ACCOUNT_ROW = {"id": 1, "name": "BBVA", "type": "bank", "currency": "EUR", "tx_count": 5, "account_number": None}
_ACCOUNT_ROW2 = {"id": 2, "name": "Indexa Capital", "type": "broker", "currency": "EUR", "tx_count": 0, "account_number": None}
_IBAN = "ES7921000813610123456789"


# ── mask_account_number unit tests ────────────────────────────────────────────

def test_mask_account_number_normal_iban():
    """24-char IBAN: country code + 18 stars + last 4."""
    result = mask_account_number(_IBAN)
    assert result.startswith("ES")
    assert result.endswith(_IBAN[-4:])
    assert "*" * (len(_IBAN) - 6) in result


def test_mask_account_number_none_returns_none():
    assert mask_account_number(None) is None


def test_mask_account_number_short_returns_as_is():
    """Numbers ≤ 6 chars are returned unchanged."""
    assert mask_account_number("ES123") == "ES123"


def test_mask_account_number_exactly_7():
    """len=7: 1 star in the middle."""
    result = mask_account_number("ES12345")
    assert result == "ES" + "*" + "2345"


def test_mask_account_number_exactly_6():
    """len=6: returned as-is (boundary)."""
    assert mask_account_number("ES1234") == "ES1234"


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
    assert set(item.keys()) == {"id", "name", "type", "currency", "tx_count", "account_number_masked"}
    assert isinstance(item["id"], int)
    assert isinstance(item["name"], str)
    assert isinstance(item["tx_count"], int)


async def test_account_type_nullable(client):
    """type field may be null per API contract."""
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [{"id": 1, "name": "Test", "type": None, "currency": "EUR", "tx_count": 0, "account_number": None}]
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


async def test_account_number_masked_none_when_absent(client):
    """account_number_masked is null for accounts with no IBAN."""
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [_ACCOUNT_ROW]
        resp = await client.get("/api/accounts")

    assert resp.json()[0]["account_number_masked"] is None


async def test_account_number_masked_applied(client):
    """account_number_masked returns the masked IBAN (not the raw IBAN)."""
    row = {**_ACCOUNT_ROW, "account_number": _IBAN}
    with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock:
        mock.return_value = [row]
        resp = await client.get("/api/accounts")

    masked = resp.json()[0]["account_number_masked"]
    assert masked is not None
    assert masked.startswith("ES")
    assert masked.endswith(_IBAN[-4:])
    assert _IBAN not in masked  # full IBAN NOT in response


# ── PATCH /api/accounts/{account_id} ─────────────────────────────────────────

async def test_patch_account_name_success(client, mock_session):
    """PATCH updates account name and returns updated AccountOut."""
    fake_account = MagicMock()
    fake_account.id = 1
    fake_account.name = "BBVA"

    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = fake_account
    mock_session.execute = AsyncMock(return_value=mock_exec_result)

    updated_row = {**_ACCOUNT_ROW, "name": "BBVA Personal", "account_number": None}
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = updated_row
        resp = await client.patch("/api/accounts/1", json={"name": "BBVA Personal"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "BBVA Personal"
    assert body["id"] == 1


async def test_patch_account_name_returns_account_out_fields(client, mock_session):
    """PATCH response includes all AccountOut fields."""
    fake_account = MagicMock()
    fake_account.id = 1

    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = fake_account
    mock_session.execute = AsyncMock(return_value=mock_exec_result)

    updated_row = {**_ACCOUNT_ROW, "name": "Nuevo Nombre", "account_number": _IBAN}
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = updated_row
        resp = await client.patch("/api/accounts/1", json={"name": "Nuevo Nombre"})

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"id", "name", "type", "currency", "tx_count", "account_number_masked"}
    assert body["account_number_masked"] is not None
    assert body["account_number_masked"].startswith("ES")


async def test_patch_account_not_found_returns_404(client, mock_session):
    """PATCH returns 404 when account does not exist."""
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_exec_result)

    resp = await client.patch("/api/accounts/99", json={"name": "Ghost"})

    assert resp.status_code == 404


async def test_patch_account_empty_name_returns_422(client):
    """PATCH rejects an empty name string."""
    resp = await client.patch("/api/accounts/1", json={"name": ""})
    assert resp.status_code == 422


async def test_patch_account_whitespace_name_returns_422(client):
    """PATCH rejects a whitespace-only name string."""
    resp = await client.patch("/api/accounts/1", json={"name": "   "})
    assert resp.status_code == 422


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
