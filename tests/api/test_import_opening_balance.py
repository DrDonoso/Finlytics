"""Edge-case tests for opening_balance in POST /api/imports/confirm.

Contract under test:
  - NEW account (by IBAN): opening_balance != 0 → opening-balance ImportRun created
    with date = min(tx_dates) - 1 day.
  - NEW account (by name): same behaviour.
  - EXISTING account: opening_balance ignored, no synthetic tx created.
  - opening_balance = 0 or None: no synthetic tx created.
  - Negative opening_balance (overdraft): tx created with negative amount.
  - Date inference: min(transaction_date) - 1, even when txs arrive out of order.
  - DB-level idempotency: dedup_hash conflict → ImportRun created but num_inserted=0.
  - Call-level idempotency: 2nd call with same account → no opening tx created.
  - Empty tx list with opening_balance → no crash, no synthetic tx.

Happy-path test lives in Shuri's PR. Only edge-cases here.

Implementation note: ``finlytics.api.imports.ImportRun`` is patched to control ids
(required so ImportResult passes Pydantic validation). The patch uses a
``side_effect`` keyed on ``source_filename`` to distinguish the opening-balance
ImportRun (source_filename="manual:saldo-inicial", mock with inspectable attributes)
from the main ImportRun (mock with id=42). Tests for "no opening tx" use a single
``return_value=fake_run``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.db.models import Account


_IBAN = "ES7921000813610123456789"
_NAME = "MiBBVA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_match() -> MagicMock:
    """execute() -> None: account does not exist."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = None
    return m


def _match(account: MagicMock) -> MagicMock:
    """execute() -> existing account."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = account
    return m


def _pg_insert_ok() -> MagicMock:
    """execute(pg_insert) -> id: INSERT succeeded."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = 999
    return m


def _pg_insert_conflict() -> MagicMock:
    """execute(pg_insert) -> None: ON CONFLICT DO NOTHING triggered."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = None
    return m


def _fake_account(account_id: int = 10, name: str = _NAME) -> MagicMock:
    acc = MagicMock(spec=Account)
    acc.id = account_id
    acc.name = name
    return acc


def _fake_main_run() -> MagicMock:
    """ImportRun mock with id=42 for the main import run."""
    run = MagicMock()
    run.id = 42
    return run


def _tx(d: str, amount: float = -10.0, account_ref: str = _NAME) -> dict:
    return {
        "transaction_date": d,
        "amount": amount,
        "currency": "EUR",
        "description": "MERCADONA",
        "category": "Groceries",
        "account_ref": account_ref,
    }


def _make_ir_side_effect(opening_run: MagicMock, main_run: MagicMock):
    """Callable for patch(ImportRun) that routes to opening or main run by source_filename.

    - source_filename contains 'saldo' → returns opening_run (propagating attributes
      for assertion inspection).
    - any other source_filename → returns main_run (id=42, valid response).
    """
    def _factory(**kw):
        sfn = kw.get("source_filename", "")
        if "saldo" in sfn.lower():
            opening_run.source_filename = sfn
            opening_run.period = kw.get("period")
            opening_run.num_parsed = kw.get("num_parsed")
            # id stays None: no real DB. pg_insert uses import_run_id=None,
            # which is harmless in tests where execute() is mocked.
            return opening_run
        return main_run
    return _factory


# ---------------------------------------------------------------------------
# TC-1: New account by IBAN + opening_balance > 0
# ---------------------------------------------------------------------------

async def test_confirm_new_iban_with_opening_balance_creates_opening_run(
    client, mock_session
):
    """New account (unseen IBAN) + opening_balance > 0 → opening-balance ImportRun created."""
    opening_run = MagicMock()
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        # _persist_import_run (imports.py) uses main_run with id=42
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        # create_opening_balance_tx (repository.py) uses its own ImportRun
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    # opening_date = 2024-06-01 - 1 = 2024-05-31 -> period "2024-05"
    assert opening_run.source_filename is not None, (
        "An opening-balance ImportRun must be created"
    )
    assert "saldo" in str(opening_run.source_filename).lower()
    assert opening_run.num_parsed == 1
    assert opening_run.period == "2024-05", (
        f"opening_date=2024-05-31 -> period='2024-05', got: {opening_run.period!r}"
    )


# ---------------------------------------------------------------------------
# TC-2: New account by NAME + opening_balance > 0
# ---------------------------------------------------------------------------

async def test_confirm_new_name_with_opening_balance_creates_opening_run(
    client, mock_session
):
    """New account (unseen name) + opening_balance > 0 → opening-balance ImportRun created."""
    opening_run = MagicMock()
    opening_run.source_filename = None  # signals "not created" if still None
    opening_run.id = None
    main_run = _fake_main_run()

    # May make 1 or 2 SELECTs by name before pg_insert;
    # extra unused side_effect items are harmless.
    mock_session.execute = AsyncMock(
        side_effect=[_no_match(), _no_match(), _pg_insert_ok()]
    )

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "source_filename": "banco.pdf",
                "opening_balance": 800.0,
                "transactions": [_tx("2024-07-15")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None, (
        "New account (by name): an opening-balance ImportRun must be created"
    )
    assert "saldo" in str(opening_run.source_filename).lower()


# ---------------------------------------------------------------------------
# TC-3: Cuenta EXISTENTE + opening_balance -> ignorado
# ---------------------------------------------------------------------------

async def test_confirm_existing_iban_opening_balance_is_ignored(
    client, mock_session
):
    """Existing account + opening_balance → no synthetic ImportRun created."""
    existing = _fake_account()
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(return_value=_match(existing))

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 9999.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    # Only 1 ImportRun created (the main one), no opening run
    assert mock_ir_class.call_count == 1, (
        "Existing account: only the main ImportRun, no opening-balance one"
    )
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-4: opening_balance = 0 -> no tx sintetica
# ---------------------------------------------------------------------------

async def test_confirm_zero_opening_balance_no_opening_tx(client, mock_session):
    """opening_balance=0 → no opening-balance ImportRun created."""
    main_run = _fake_main_run()
    mock_session.execute = AsyncMock(return_value=_no_match())

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 0.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert mock_ir_class.call_count == 1, "opening_balance=0 → only 1 ImportRun"
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-5: opening_balance = null -> no tx sintetica
# ---------------------------------------------------------------------------

async def test_confirm_null_opening_balance_no_opening_tx(client, mock_session):
    """opening_balance omitted (None) → no opening-balance ImportRun created."""
    main_run = _fake_main_run()
    mock_session.execute = AsyncMock(return_value=_no_match())

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert mock_ir_class.call_count == 1, "opening_balance=null → only 1 ImportRun"


# ---------------------------------------------------------------------------
# TC-6: opening_balance negativo (sobregiro)
# ---------------------------------------------------------------------------

async def test_confirm_negative_opening_balance_creates_opening_run(
    client, mock_session
):
    """Negative opening_balance → opening-balance ImportRun created (negative amount is valid)."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": -500.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None, (
        "Negative opening_balance must create an opening-balance ImportRun"
    )
    assert "saldo" in str(opening_run.source_filename).lower()
    assert opening_run.num_parsed == 1


# ---------------------------------------------------------------------------
# TC-7: Inferencia de fecha -- earliest tx - 1 dia (txs desordenadas)
# ---------------------------------------------------------------------------

async def test_confirm_opening_tx_date_is_earliest_tx_minus_one_day(
    client, mock_session
):
    """opening_date = min(transaction_date) - 1 day, even when txs arrive out of order."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    # Out-of-order txs: minimum is 2024-05-01 → opening_date = 2024-04-30 → period "2024-04"
    transactions = [
        _tx("2024-06-15"),
        _tx("2024-05-01"),  # <- minimum
        _tx("2024-06-01"),
    ]

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(3, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": transactions,
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None
    # min(2024-06-15, 2024-05-01, 2024-06-01) = 2024-05-01
    # opening_date = 2024-04-30 -> period = "2024-04"
    assert opening_run.period == "2024-04", (
        f"Out-of-order txs: opening_date must be 2024-04-30 (min-1), "
        f"period='2024-04'. Got: {opening_run.period!r}"
    )


# ---------------------------------------------------------------------------
# TC-8a: Idempotencia DB-level (conflicto dedup_hash)
# ---------------------------------------------------------------------------

async def test_confirm_opening_tx_dedup_conflict_sets_num_inserted_zero(
    client, mock_session
):
    """ON CONFLICT DO NOTHING → ImportRun created but num_inserted=0, num_duplicates=1."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    # pg_insert returns None → scalar_one_or_none()=None → conflict triggered
    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_conflict()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1000.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None, (
        "The opening-balance ImportRun must be created even with a dedup conflict"
    )
    # These attributes are set after execute():
    assert opening_run.num_inserted == 0, (
        "dedup_hash conflict: num_inserted must be 0"
    )
    assert opening_run.num_duplicates == 1, (
        "dedup_hash conflict: num_duplicates must be 1"
    )


# ---------------------------------------------------------------------------
# TC-8b: Idempotencia call-level (2a llamada con cuenta existente)
# ---------------------------------------------------------------------------

async def test_confirm_second_call_existing_account_no_opening_tx(
    client, mock_session
):
    """2nd confirm with the same account (already created) → opening_balance ignored."""
    existing = _fake_account(account_id=15)
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(return_value=_match(existing))

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(2, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco2.pdf",
                "opening_balance": 1500.0,
                "transactions": [_tx("2024-07-01"), _tx("2024-07-15")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert mock_ir_class.call_count == 1, (
        "2nd call (existing account): only the main ImportRun, no opening-balance one"
    )
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-9: Lista vacia de txs + opening_balance -> sin crash, sin opening tx
# ---------------------------------------------------------------------------

async def test_confirm_empty_transactions_with_opening_balance_no_crash(
    client, mock_session
):
    """transactions=[] with opening_balance → 200 OK, no synthetic tx.

    Potential bug: min() on an empty list raises ValueError if
    the opening_date calculation block lacks an upfront guard.
    """
    main_run = _fake_main_run()

    # With no txs, pg_insert must not be reached → one execute (IBAN SELECT)
    mock_session.execute = AsyncMock(return_value=_no_match())

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(0, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": [],
            },
        )

    assert resp.status_code == 200, (
        f"transactions=[] + opening_balance must not crash. "
        f"Got {resp.status_code}: {resp.text}"
    )
    assert mock_ir_class.call_count == 1, (
        "No txs: only the main ImportRun, no opening-balance one"
    )
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-10: Sanidad -- response estructura valida con opening_balance
# ---------------------------------------------------------------------------

async def test_confirm_with_opening_balance_returns_valid_import_result(
    client, mock_session
):
    """The endpoint returns a complete, valid ImportResult even with opening_balance set."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(2, 0)),
        patch("finlytics.api.imports.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": [_tx("2024-06-01"), _tx("2024-06-15")],
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) >= {"import_run_id", "num_parsed", "num_inserted", "num_duplicates"}
    assert body["import_run_id"] == 42  # ID of the main ImportRun (main_run.id)
    assert body["num_parsed"] == 2
    assert body["num_inserted"] == 2
    assert body["num_duplicates"] == 0
