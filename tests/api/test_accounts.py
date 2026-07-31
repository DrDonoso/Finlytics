"""Tests for GET /api/accounts, PATCH /api/accounts/{id}, DELETE /api/accounts/{id}, and POST /api/accounts."""

from datetime import date as _date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.api.schemas import mask_account_number
from finlytics.db.models import Account, ImportRun
from finlytics.db.repository import compute_dedup_hash


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

    updated_row = {**_ACCOUNT_ROW, "name": "New Name", "account_number": _IBAN}
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = updated_row
        resp = await client.patch("/api/accounts/1", json={"name": "New Name"})

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


# ── POST /api/accounts ────────────────────────────────────────────────────────

def _make_no_conflict_session(mock_session: MagicMock) -> MagicMock:
    """Helper: configure mock_session so uniqueness checks find nothing."""
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=no_conflict)
    return mock_session


async def test_create_account_minimal_returns_201(client, mock_session):
    """POST /api/accounts with name only returns 201 and AccountOut fields."""
    _make_no_conflict_session(mock_session)
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW, "name": "Santander"}
        resp = await client.post("/api/accounts", json={"name": "Santander"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Santander"
    assert body["type"] == "bank"
    assert body["currency"] == "EUR"
    assert set(body.keys()) == {"id", "name", "type", "currency", "tx_count", "account_number_masked"}


async def test_create_account_custom_type_and_currency(client, mock_session):
    """POST /api/accounts accepts custom type and currency."""
    _make_no_conflict_session(mock_session)
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"id": 2, "name": "ING", "type": "savings", "currency": "USD", "tx_count": 0, "account_number": None}
        resp = await client.post("/api/accounts", json={"name": "ING", "type": "savings", "currency": "USD"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "savings"
    assert body["currency"] == "USD"


async def test_create_account_with_opening_balance_returns_201(client, mock_session):
    """POST /api/accounts with opening_balance creates account + returns 201."""
    _make_no_conflict_session(mock_session)
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW, "name": "BBVA", "tx_count": 1}
        resp = await client.post("/api/accounts", json={
            "name": "BBVA",
            "opening_balance": 1500.0,
            "opening_date": "2026-01-01",
        })

    assert resp.status_code == 201
    assert resp.json()["tx_count"] == 1


async def test_create_account_zero_opening_balance_no_transaction(client, mock_session):
    """opening_balance=0 creates the account but NOT a transaction (tx_count=0)."""
    _make_no_conflict_session(mock_session)
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW, "tx_count": 0}
        resp = await client.post("/api/accounts", json={
            "name": "BBVA",
            "opening_balance": 0.0,
            "opening_date": "2026-01-01",
        })

    assert resp.status_code == 201
    # add was called once (Account only) — no ImportRun, no Transaction
    session_add_calls = mock_session.add.call_count
    assert session_add_calls == 1


async def test_create_account_duplicate_name_returns_409(client, mock_session):
    """POST returns 409 when an account with the same name already exists."""
    existing = MagicMock()
    existing.id = 99
    conflict_result = MagicMock()
    conflict_result.scalar_one_or_none.return_value = existing
    mock_session.execute = AsyncMock(return_value=conflict_result)

    resp = await client.post("/api/accounts", json={"name": "BBVA"})
    assert resp.status_code == 409


async def test_create_account_duplicate_iban_returns_409(client, mock_session):
    """POST returns 409 when account_number already belongs to another account."""
    # First call (name check) → no conflict; second call (IBAN check) → conflict
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    existing = MagicMock()
    existing.id = 5
    conflict = MagicMock()
    conflict.scalar_one_or_none.return_value = existing
    mock_session.execute = AsyncMock(side_effect=[no_conflict, conflict])

    resp = await client.post("/api/accounts", json={"name": "NewAccount", "account_number": _IBAN})
    assert resp.status_code == 409


async def test_create_account_opening_balance_without_date_returns_422(client):
    """opening_balance provided without opening_date → 422 (Pydantic model_validator)."""
    resp = await client.post("/api/accounts", json={"name": "BBVA", "opening_balance": 1000.0})
    assert resp.status_code == 422


async def test_create_account_empty_name_returns_422(client):
    """POST rejects an empty name."""
    resp = await client.post("/api/accounts", json={"name": ""})
    assert resp.status_code == 422


async def test_create_account_whitespace_name_trimmed_to_empty_returns_422(client):
    """POST rejects a whitespace-only name."""
    resp = await client.post("/api/accounts", json={"name": "   "})
    assert resp.status_code == 422


async def test_create_account_with_iban_masked_in_response(client, mock_session):
    """account_number_masked in response uses mask, not raw IBAN."""
    _make_no_conflict_session(mock_session)
    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW, "account_number": _IBAN}
        resp = await client.post("/api/accounts", json={"name": "BBVA", "account_number": _IBAN})

    assert resp.status_code == 201
    body = resp.json()
    assert body["account_number_masked"] is not None
    assert _IBAN not in body["account_number_masked"]
    assert body["account_number_masked"].startswith("ES")
    assert body["account_number_masked"].endswith(_IBAN[-4:])


# ── POST /api/accounts — edge-case tests (Barton, QA) ────────────────────────
#
# Shuri's tests cover happy path, schema shape, and basic duplicate detection.
# These tests cover the seams: negative balance, ImportRun metadata, dedup-hash
# determinism, zero-balance guard (type-level), and account attribute pass-through.
#
# Implementation notes from accounts.py:
#   • Duplicate checks: SELECT-first (not IntegrityError) → 409
#   • Transaction: pg_insert via session.execute (not session.add)
#   • ImportRun IS created via session.add — inspectable to verify tx creation
#   • opening_balance == 0 → treated as absent, no ImportRun / no transaction
#   • Pydantic model_validator enforces opening_date required with opening_balance


def _pg_insert_ok() -> MagicMock:
    """Execute result simulating a successful pg_insert (tx was actually inserted)."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = 999  # a real tx.id would be returned
    return m


def _track_session_adds(mock_session: MagicMock) -> list:
    """Capture each object passed to session.add() for type inspection."""
    added: list = []
    mock_session.add.side_effect = lambda obj: added.append(obj)
    return added


# 6. Negative opening_balance → 201, dedup-hash computed with negative amount

async def test_create_account_negative_opening_balance_201(client, mock_session):
    """Negative opening_balance (overdraft) → 201; amount in dedup_hash is negative."""
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(side_effect=[no_conflict, _pg_insert_ok()])

    with (
        patch("finlytics.db.repository.compute_dedup_hash", wraps=compute_dedup_hash) as mock_hash,
        patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = {**_ACCOUNT_ROW, "name": "Overdraft", "tx_count": 1}
        resp = await client.post("/api/accounts", json={
            "name": "Overdraft",
            "opening_balance": -250.00,
            "opening_date": "2024-03-15",
        })

    assert resp.status_code == 201
    assert mock_hash.called, "compute_dedup_hash must be called for a non-zero opening_balance"
    called_amount = mock_hash.call_args.kwargs["amount"]
    assert float(called_amount) < 0, f"Expected negative amount, got {called_amount}"
    assert float(called_amount) == pytest.approx(-250.0)


# 2b. Opening transaction: description, transaction_date, amount all verified

async def test_create_account_opening_transaction_fields(client, mock_session):
    """'Saldo inicial' transaction is computed with correct description, date, and amount."""
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(side_effect=[no_conflict, _pg_insert_ok()])

    with (
        patch("finlytics.db.repository.compute_dedup_hash", wraps=compute_dedup_hash) as mock_hash,
        patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = {**_ACCOUNT_ROW, "tx_count": 1}
        resp = await client.post("/api/accounts", json={
            "name": "BBVA",
            "opening_balance": 3000.00,
            "opening_date": "2024-06-15",
        })

    assert resp.status_code == 201
    assert mock_hash.called
    kwargs = mock_hash.call_args.kwargs
    assert kwargs["description"] == "Saldo inicial", "Transaction description must be 'Saldo inicial'"
    assert kwargs["transaction_date"] == _date(2024, 6, 15), "Transaction date must equal opening_date"
    assert float(kwargs["amount"]) == pytest.approx(3000.0), "Transaction amount must equal opening_balance"
    # balance_after is set to amount in the pg_insert (same value); verified by code inspection


# 9. dedup_hash is deterministic and 64-char hex

async def test_create_account_opening_transaction_dedup_hash_deterministic(client, mock_session):
    """dedup_hash is computed from (account_name, opening_date, amount, 'Saldo inicial')."""
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(side_effect=[no_conflict, _pg_insert_ok()])

    with (
        patch("finlytics.db.repository.compute_dedup_hash", wraps=compute_dedup_hash) as mock_hash,
        patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = {**_ACCOUNT_ROW, "tx_count": 1}
        resp = await client.post("/api/accounts", json={
            "name": "BBVA",
            "opening_balance": 500.00,
            "opening_date": "2024-06-01",
        })

    assert resp.status_code == 201
    assert mock_hash.called
    kwargs = mock_hash.call_args.kwargs
    assert kwargs["account_ref"] == "BBVA"
    assert kwargs["description"] == "Saldo inicial"

    expected_hash = compute_dedup_hash(
        account_ref="BBVA",
        transaction_date=_date(2024, 6, 1),
        amount=Decimal("500.00"),
        description="Saldo inicial",
    )
    assert len(expected_hash) == 64, "SHA-256 hex digest must be 64 chars"
    assert all(c in "0123456789abcdef" for c in expected_hash)
    # Re-compute with same inputs → identical hash (determinism)
    assert expected_hash == compute_dedup_hash(
        account_ref="BBVA",
        transaction_date=_date(2024, 6, 1),
        amount=Decimal("500.00"),
        description="Saldo inicial",
    )


# 2c. ImportRun metadata for the synthetic opening run

async def test_create_account_opening_import_run_metadata(client, mock_session):
    """Opening ImportRun has source_filename='manual:saldo-inicial' and correct ISO period."""
    added = _track_session_adds(mock_session)
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(side_effect=[no_conflict, _pg_insert_ok()])

    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW, "tx_count": 1}
        resp = await client.post("/api/accounts", json={
            "name": "BBVA",
            "opening_balance": 1000.00,
            "opening_date": "2024-06-15",
        })

    assert resp.status_code == 201
    import_runs = [o for o in added if isinstance(o, ImportRun)]
    assert len(import_runs) == 1, "Exactly one ImportRun must be created for a non-zero opening_balance"
    ir = import_runs[0]
    assert ir.source_filename == "manual:saldo-inicial"
    assert ir.period == "2024-06"


# 7b. opening_balance=0 → no ImportRun (type-level check, not just call_count)

async def test_create_account_zero_opening_balance_no_import_run(client, mock_session):
    """opening_balance=0 is treated as absent — no ImportRun is added to the session."""
    added = _track_session_adds(mock_session)
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=no_conflict)

    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW, "name": "Empty", "tx_count": 0}
        resp = await client.post("/api/accounts", json={
            "name": "Empty",
            "opening_balance": 0.0,
            "opening_date": "2024-01-01",
        })

    assert resp.status_code == 201
    import_runs = [o for o in added if isinstance(o, ImportRun)]
    assert import_runs == [], "opening_balance=0 must NOT create an ImportRun or transaction"
    accounts = [o for o in added if isinstance(o, Account)]
    assert len(accounts) == 1, "Exactly one Account must be added to the session"


# 8c. Currency is passed through to the Account ORM object

async def test_create_account_currency_stored_on_account_object(client, mock_session):
    """Default EUR and custom currencies are stored on the Account ORM object."""
    # EUR default
    added_eur: list = []
    mock_session.add.side_effect = lambda obj: added_eur.append(obj)
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=no_conflict)

    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW}
        resp = await client.post("/api/accounts", json={"name": "Default EUR"})

    assert resp.status_code == 201
    accounts_eur = [o for o in added_eur if isinstance(o, Account)]
    assert accounts_eur[0].currency == "EUR"


async def test_create_account_usd_currency_stored_on_account_object(client, mock_session):
    """Non-default currency is forwarded to the Account ORM object."""
    added = _track_session_adds(mock_session)
    no_conflict = MagicMock()
    no_conflict.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=no_conflict)

    with patch("finlytics.db.queries.get_account_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {**_ACCOUNT_ROW, "currency": "USD"}
        resp = await client.post("/api/accounts", json={"name": "US Account", "currency": "USD"})

    assert resp.status_code == 201
    accounts = [o for o in added if isinstance(o, Account)]
    assert accounts[0].currency == "USD"

