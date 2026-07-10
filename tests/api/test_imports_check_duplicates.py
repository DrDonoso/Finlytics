"""Tests for POST /api/imports/check-duplicates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from finlytics.db.repository import compute_dedup_hash


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tx(
    *,
    transaction_date: str = "2024-06-01",
    amount: float = -42.5,
    description: str = "MERCADONA",
    detail: str | None = None,
) -> dict:
    d = {
        "transaction_date": transaction_date,
        "amount": amount,
        "description": description,
    }
    if detail is not None:
        d["detail"] = detail
    return d


def _expected_hash(
    account_name: str,
    *,
    transaction_date: str = "2024-06-01",
    amount: float = -42.5,
    description: str = "MERCADONA",
    detail: str | None = None,
) -> str:
    """Compute hash the same way the endpoint does (Decimal from str avoids float imprecision)."""
    return compute_dedup_hash(
        account_ref=account_name,
        transaction_date=date.fromisoformat(transaction_date),
        amount=Decimal(str(amount)),
        description=description,
        detail=detail,
    )


def _mock_db_result(hashes: list[str], mock_session: MagicMock) -> None:
    """Configure mock_session.execute to return the given hashes from scalars().all()."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = hashes
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)


# ── Core behaviour ────────────────────────────────────────────────────────────

async def test_check_duplicates_empty_list(client, mock_session):
    """Empty input → empty is_duplicate list, no DB query needed."""
    mock_session.execute = AsyncMock()  # should not be called
    resp = await client.post(
        "/api/imports/check-duplicates",
        json={"account_name": "BBVA", "transactions": []},
    )
    assert resp.status_code == 200
    assert resp.json() == {"is_duplicate": []}
    mock_session.execute.assert_not_called()


async def test_check_duplicates_all_new(client, mock_session):
    """No hashes found in DB → all False."""
    _mock_db_result([], mock_session)
    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": "BBVA",
            "transactions": [_tx(), _tx(description="LIDL", amount=-10.0)],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [False, False]


async def test_check_duplicates_all_existing(client, mock_session):
    """All hashes found in DB → all True."""
    account = "BBVA"
    h0 = _expected_hash(account)
    h1 = _expected_hash(account, description="LIDL", amount=-10.0)
    _mock_db_result([h0, h1], mock_session)

    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": account,
            "transactions": [_tx(), _tx(description="LIDL", amount=-10.0)],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [True, True]


async def test_check_duplicates_mixed(client, mock_session):
    """First tx exists in DB, second is new → [True, False]."""
    account = "BBVA"
    h0 = _expected_hash(account)
    _mock_db_result([h0], mock_session)

    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": account,
            "transactions": [_tx(), _tx(description="LIDL", amount=-10.0)],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [True, False]


async def test_check_duplicates_response_order_matches_input(client, mock_session):
    """is_duplicate has same length and order as input transactions."""
    account = "BBVA"
    txs = [
        _tx(description="A", amount=-1.0),
        _tx(description="B", amount=-2.0),
        _tx(description="C", amount=-3.0),
    ]
    h_b = _expected_hash(account, description="B", amount=-2.0)
    _mock_db_result([h_b], mock_session)

    resp = await client.post(
        "/api/imports/check-duplicates",
        json={"account_name": account, "transactions": txs},
    )
    assert resp.status_code == 200
    result = resp.json()["is_duplicate"]
    assert len(result) == 3
    assert result == [False, True, False]


# ── Intra-batch duplicates ────────────────────────────────────────────────────

async def test_check_duplicates_intra_batch_second_occurrence_flagged(client, mock_session):
    """Same transaction twice; neither in DB → first=False, second=True."""
    _mock_db_result([], mock_session)
    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": "BBVA",
            "transactions": [_tx(), _tx()],  # identical
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [False, True]


async def test_check_duplicates_intra_batch_third_occurrence_also_flagged(client, mock_session):
    """Same transaction three times → [False, True, True]."""
    _mock_db_result([], mock_session)
    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": "BBVA",
            "transactions": [_tx(), _tx(), _tx()],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [False, True, True]


async def test_check_duplicates_intra_batch_already_in_db(client, mock_session):
    """Same transaction twice; first occurrence IS in DB → both flagged True."""
    account = "BBVA"
    h = _expected_hash(account)
    _mock_db_result([h], mock_session)

    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": account,
            "transactions": [_tx(), _tx()],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [True, True]


# ── Hash consistency (matches what confirm would skip) ───────────────────────

async def test_check_duplicates_hash_matches_compute_dedup_hash(client, mock_session):
    """Endpoint uses compute_dedup_hash with the same inputs → hash is correct."""
    account = "BBVA"
    tx_date = "2024-06-01"
    amount = -42.5
    description = "MERCADONA"
    detail = "GCREOCTOPUSENERGY"

    known_hash = compute_dedup_hash(
        account_ref=account,
        transaction_date=date.fromisoformat(tx_date),
        amount=Decimal(str(amount)),
        description=description,
        detail=detail,
    )
    _mock_db_result([known_hash], mock_session)

    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": account,
            "transactions": [_tx(transaction_date=tx_date, amount=amount,
                                 description=description, detail=detail)],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [True]


async def test_check_duplicates_hash_with_null_detail(client, mock_session):
    """Hash with null detail matches the pre-detail formula (backward compat)."""
    account = "TestBank"
    # Use _expected_hash (Decimal(str(amount))) so the float→Decimal path matches
    # exactly what Pydantic produces when parsing the JSON number.
    known_hash = _expected_hash(
        account,
        transaction_date="2024-01-15",
        amount=-100.0,
        description="SALARY",
        detail=None,
    )
    _mock_db_result([known_hash], mock_session)

    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": account,
            "transactions": [
                {"transaction_date": "2024-01-15", "amount": -100.0, "description": "SALARY"}
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [True]


async def test_check_duplicates_account_name_is_used_in_hash(client, mock_session):
    """Different account names produce different hashes; only the right one matches."""
    account_a = "BBVA"
    account_b = "CaixaBank"
    h_a = _expected_hash(account_a)
    # DB contains h_a only
    _mock_db_result([h_a], mock_session)

    resp = await client.post(
        "/api/imports/check-duplicates",
        json={
            "account_name": account_b,  # different account — hash won't match h_a
            "transactions": [_tx()],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_duplicate"] == [False]


# ── Auth guard ────────────────────────────────────────────────────────────────

async def test_check_duplicates_requires_auth(mock_session):
    """Endpoint protected — missing auth cookie → 401."""
    from httpx import ASGITransport, AsyncClient
    from finlytics.api.deps import get_db
    from finlytics.app import app

    async def _override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/imports/check-duplicates",
                json={"account_name": "BBVA", "transactions": []},
            )
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)
