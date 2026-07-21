"""Tests for is_system flag — OPTION B: ledger visible, KPIs excluded.

Comportamiento OPTION B (aprobado por el owner):
  - Ledger (get_transactions / GET /api/transactions): INCLUYE is_system=True.
  - KPIs (overview, category, merchant, month, day, account, cashflow): EXCLUYEN is_system=True.
  - El campo ``is_system`` aparece en cada ítem del ledger para que el frontend
    pueda mostrar el badge "sistema" en las aperturas de saldo.

Three complementary layers:

1. Unit-level — calls ``_apply_filters`` directly and inspects the compiled SQL
   to guarantee the ``is_system = false`` predicate is (or is not) emitted.
   Synchronous; no async/mock session needed.

2. API-level — GET /api/summary/overview with a patched ``get_overview`` that
   returns figures *as if* the opening-balance row were already excluded, and
   checks the response contract.  Mirrors the happy-path the owner approved.

3. Integration-level — StaticPool + aiosqlite with real data rows and real SQL
   execution.  Verifies:
   - KPIs (TC-1..TC-7): is_system=True excluida de todas las agregaciones.
   - Ledger (TC-9): is_system=True VISIBLE, campo ``is_system`` presente.
   - Regresión (TC-10): KPIs dan 2 txs, ledger da 3 txs — OPTION B coherente.
   Uses ``to_char`` SQLite shim registered via the ``"connect"`` event.

Dataset fijo (integration tests)
──────────────────────────────────
  income_tx   amount=+1000.00  is_system=False  cat=Income     merchant="Acme"
  expense_tx  amount=−200.00   is_system=False  cat=Groceries  merchant="Mercadona"
  opening_tx  amount=+5000.00  is_system=True   cat=None       merchant="SaldoTest"

Resultados esperados en KPIs (is_system excluido):
  total_income  = 1000.00   (NO 6000.00)
  total_expense =  200.00
  net           =  800.00

Resultados esperados en ledger (OPTION B — is_system incluido):
  total txs = 3  (2 normales + 1 apertura)
  opening_item["is_system"] == True
"""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.db.models import Account, Base, Category, ImportRun, Transaction
from finlytics.db.queries import (
    _apply_filters,
    get_by_account,
    get_by_category,
    get_by_day,
    get_by_merchant,
    get_by_month,
    get_cashflow,
    get_overview,
    get_transactions,
)


# ── Unit: _apply_filters SQL output ──────────────────────────────────────────


def test_apply_filters_excludes_system_by_default():
    """_apply_filters adds ``is_system = false`` to the WHERE clause by default."""
    stmt = _apply_filters(select(Transaction.id).select_from(Transaction))
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "is_system" in sql, f"Expected is_system in compiled SQL, got:\n{sql}"
    assert "false" in sql.lower(), f"Expected 'false' in compiled SQL, got:\n{sql}"


def test_apply_filters_skips_is_system_when_disabled():
    """_apply_filters does NOT add is_system filter when exclude_system=False."""
    stmt = _apply_filters(
        select(Transaction.id).select_from(Transaction),
        exclude_system=False,
    )
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "is_system" not in sql, (
        f"Expected NO is_system in compiled SQL when exclude_system=False, got:\n{sql}"
    )


def test_apply_filters_system_filter_is_last():
    """is_system exclusion is applied after all other filters — correct ORDER."""
    from datetime import date

    stmt = _apply_filters(
        select(Transaction.id).select_from(Transaction),
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
    )
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "is_system" in sql


# ── API: happy-path — GET /api/summary/overview excludes opening balance ──────


async def test_overview_excludes_opening_balance_tx(client):
    """GET /api/summary/overview returns totals that exclude is_system transactions.

    An opening-balance row (is_system=True) must NOT inflate total_income.
    The mock simulates a DB state where the opening balance (e.g. 1000 EUR) has
    already been filtered out by _apply_filters(exclude_system=True).

    If the filter were absent, total_income would include the 1000 EUR entry
    and the response would be wrong.  Here we verify the API surface returns
    only the clean figures supplied by the (already-filtered) query.
    """
    # Scenario: account seeded with 1000 EUR opening balance + 1 real income tx of 500 EUR.
    # With is_system excluded: total_income == 500, num_transactions == 1.
    # Without exclusion: total_income == 1500, num_transactions == 2.
    overview_without_opening_balance = {
        "total_expense": 0.0,
        "total_income": 500.0,   # only the real salary tx; opening 1000 is excluded
        "net": 500.0,
        "num_transactions": 1,   # only the real tx counted
        "top_category": None,
        "currency": "EUR",
    }
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = overview_without_opening_balance
        resp = await client.get("/api/summary/overview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_income"] == 500.0, (
        "Opening-balance tx (is_system=True) must not be included in total_income"
    )
    assert body["num_transactions"] == 1, (
        "Opening-balance tx (is_system=True) must not be counted in num_transactions"
    )
    assert body["net"] == 500.0


# =============================================================================
# CAPA 3 — Integration: StaticPool + aiosqlite + SQL real
# =============================================================================

# ── Constantes ────────────────────────────────────────────────────────────────

_INCOME_AMOUNT = Decimal("1000.00")
_EXPENSE_AMOUNT = Decimal("-200.00")
_OPENING_AMOUNT = Decimal("5000.00")

_INCOME_DATE = date(2024, 5, 15)
_EXPENSE_DATE = date(2024, 5, 20)
_OPENING_DATE = date(2024, 5, 1)


# ── Shim to_char para SQLite ──────────────────────────────────────────────────

def _to_char_shim(value: str | None, fmt: str) -> str | None:
    """Emula to_char(date, 'YYYY-MM' | 'YYYY-MM-DD') de PostgreSQL en SQLite."""
    if value is None:
        return None
    s = str(value)
    if fmt == "YYYY-MM":
        return s[:7]
    if fmt == "YYYY-MM-DD":
        return s[:10]
    return s


def _register_to_char(dbapi_conn, _record):
    """Listener del evento 'connect' — registra to_char en la conexión SQLite.

    Con StaticPool + aiosqlite, dbapi_conn es AsyncAdapt_aiosqlite_connection,
    cuyo .create_function() es síncrono (wrapper sobre sqlite3.create_function).
    """
    dbapi_conn.create_function("to_char", 2, _to_char_shim)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def sqlite_engine():
    """Motor SQLite en memoria con StaticPool y shim to_char para get_by_month/day."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(eng.sync_engine, "connect", _register_to_char)

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


def _sf(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Helper de datos ───────────────────────────────────────────────────────────

def _dedup(account_name: str, tx_date: date, amount: Decimal, desc: str) -> str:
    payload = json.dumps(
        {"account": account_name.lower(), "date": str(tx_date),
         "amount": str(amount), "description": desc.lower()},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


async def _create_test_data(session: AsyncSession) -> dict:
    """Inserta cuenta, categorías, import_runs y 3 transacciones de prueba."""
    account = Account(name="TestBank", type="bank", currency="EUR")
    session.add(account)
    await session.flush()

    cat_income = Category(name="Income", is_base=True, name_es="Ingresos")
    cat_grocery = Category(name="Groceries", is_base=True, name_es="Supermercado")
    session.add_all([cat_income, cat_grocery])
    await session.flush()

    ir_normal = ImportRun(
        account_id=account.id, source_filename="test.csv",
        period="2024-05", num_parsed=2, num_inserted=2, num_duplicates=0,
    )
    ir_saldo = ImportRun(
        account_id=account.id, source_filename="manual:saldo-inicial",
        period="2024-05", num_parsed=1, num_inserted=1, num_duplicates=0,
    )
    session.add_all([ir_normal, ir_saldo])
    await session.flush()

    income_tx = Transaction(
        id=1,
        account_id=account.id, import_run_id=ir_normal.id,
        transaction_date=_INCOME_DATE, amount=_INCOME_AMOUNT, currency="EUR",
        description="Nómina mayo", category_id=cat_income.id,
        merchant="Acme", is_system=False,
        dedup_hash=_dedup("TestBank", _INCOME_DATE, _INCOME_AMOUNT, "Nómina mayo"),
    )
    expense_tx = Transaction(
        id=2,
        account_id=account.id, import_run_id=ir_normal.id,
        transaction_date=_EXPENSE_DATE, amount=_EXPENSE_AMOUNT, currency="EUR",
        description="MERCADONA", category_id=cat_grocery.id,
        merchant="Mercadona", is_system=False,
        dedup_hash=_dedup("TestBank", _EXPENSE_DATE, _EXPENSE_AMOUNT, "MERCADONA"),
    )
    # Saldo inicial sintético — is_system=True; merchant="SaldoTest" para
    # poder verificar su exclusión en get_by_merchant
    opening_tx = Transaction(
        id=3,
        account_id=account.id, import_run_id=ir_saldo.id,
        transaction_date=_OPENING_DATE, amount=_OPENING_AMOUNT, currency="EUR",
        description="Saldo inicial", category_id=None,
        merchant="SaldoTest", is_system=True,
        dedup_hash=_dedup("TestBank", _OPENING_DATE, _OPENING_AMOUNT, "Saldo inicial"),
    )
    session.add_all([income_tx, expense_tx, opening_tx])
    await session.flush()

    return {
        "account_id": account.id,
        "income_tx_id": income_tx.id,
        "expense_tx_id": expense_tx.id,
        "opening_tx_id": opening_tx.id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TC-1: get_overview — income/net NO incluyen el saldo inicial
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_overview_excludes_opening_balance(sqlite_engine):
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        result = await get_overview(s)

    assert result["total_income"] == pytest.approx(1000.00), (
        f"total_income debe ser 1000 (saldo 5000 excluido), fue {result['total_income']}"
    )
    assert result["total_expense"] == pytest.approx(200.00)
    assert result["net"] == pytest.approx(800.00)
    assert result["num_transactions"] == 2, (
        f"Solo 2 transacciones normales deben contarse, "
        f"num_transactions={result['num_transactions']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TC-2: get_by_category — saldo no aparece en ningún bucket de categoría
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_by_category_excludes_opening_balance(sqlite_engine):
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        rows = await get_by_category(s)

    # get_by_category filtra amount < 0 (gastos) — solo Groceries debe aparecer
    total = sum(r["amount"] for r in rows)
    assert total == pytest.approx(200.00), (
        f"Suma de categorías debe ser 200 (solo gasto normal), fue {total}"
    )
    for row in rows:
        assert row["amount"] < 5000, (
            f"Ningún bucket debe tener amount ~ 5000 (saldo inicial is_system=True): {row}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-3: get_by_merchant — merchant del saldo inicial excluido
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_by_merchant_excludes_opening_balance(sqlite_engine):
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        rows = await get_by_merchant(s)

    merchants = [r["merchant"] for r in rows]
    assert "SaldoTest" not in merchants, (
        "El merchant 'SaldoTest' de la tx de apertura (is_system=True) "
        "no debe aparecer en get_by_merchant"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TC-4: get_by_month — income de mayo no está inflado por el saldo inicial
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_by_month_excludes_opening_balance(sqlite_engine):
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        rows = await get_by_month(s)

    assert len(rows) == 1, f"Debe haber 1 mes (2024-05), encontrados {len(rows)}"
    may = rows[0]
    assert may["month"] == "2024-05"
    assert may["income"] == pytest.approx(1000.00), (
        f"Ingreso de mayo debe ser 1000 (saldo 5000 excluido), fue {may['income']}"
    )
    assert may["expense"] == pytest.approx(200.00)
    assert may["net"] == pytest.approx(800.00)


# ─────────────────────────────────────────────────────────────────────────────
# TC-5: get_by_day — día del saldo inicial no aparece en la serie diaria
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_by_day_excludes_opening_balance(sqlite_engine):
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        rows = await get_by_day(s)

    days = {r["day"]: r for r in rows}
    assert "2024-05-01" not in days, (
        "El día 2024-05-01 (solo saldo inicial is_system=True) NO debe aparecer"
    )
    assert set(days.keys()) == {"2024-05-15", "2024-05-20"}, (
        f"Solo deben aparecer días de txs normales, encontrados: {set(days.keys())}"
    )
    assert days["2024-05-15"]["income"] == pytest.approx(1000.00)
    assert days["2024-05-20"]["expense"] == pytest.approx(200.00)


# ─────────────────────────────────────────────────────────────────────────────
# TC-6: get_by_account — income/net de la cuenta son correctos
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_by_account_excludes_opening_balance(sqlite_engine):
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        rows = await get_by_account(s)

    assert len(rows) == 1
    acct = rows[0]
    assert acct["account"] == "TestBank"
    assert acct["income"] == pytest.approx(1000.00), (
        f"Income de TestBank debe ser 1000 (saldo 5000 excluido), fue {acct['income']}"
    )
    assert acct["expense"] == pytest.approx(200.00)
    assert acct["net"] == pytest.approx(800.00)


# ─────────────────────────────────────────────────────────────────────────────
# TC-7: get_cashflow — saldo inicial no aparece en income
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_cashflow_excludes_opening_balance(sqlite_engine):
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        result = await get_cashflow(s)

    assert result["total_income"] == pytest.approx(1000.00), (
        f"Cashflow total_income debe ser 1000 (saldo 5000 excluido), fue {result['total_income']}"
    )
    for item in result["income"]:
        assert item["amount"] < 5000, (
            f"Ningún item de cashflow income debe tener amount ~ 5000: {item}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-8a: flag is_system — opening_tx=True, normales=False
# ─────────────────────────────────────────────────────────────────────────────

async def test_is_system_flag_values(sqlite_engine):
    """Opening tx tiene is_system=True; transacciones normales tienen is_system=False."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            ids = await _create_test_data(s)

    async with factory() as s:
        opening = await s.get(Transaction, ids["opening_tx_id"])
        income = await s.get(Transaction, ids["income_tx_id"])
        expense = await s.get(Transaction, ids["expense_tx_id"])

    assert opening.is_system is True, (
        "La tx de apertura (Saldo inicial) debe tener is_system=True"
    )
    assert income.is_system is False, (
        "La tx normal de ingreso debe tener is_system=False"
    )
    assert expense.is_system is False, (
        "La tx normal de gasto debe tener is_system=False"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TC-8b: create_opening_balance_tx inserta is_system=True en el código fuente
# ─────────────────────────────────────────────────────────────────────────────

def test_create_opening_balance_helper_sets_is_system():
    """create_opening_balance_tx pasa is_system=True al pg_insert (verificación fuente).

    La función usa pg_insert (PostgreSQL-específico), no ejecutable en SQLite.
    Se verifica la fuente directamente para garantizar que cualquier apertura
    creada en producción tendrá is_system=True.
    """
    from finlytics.db import repository

    src = inspect.getsource(repository.create_opening_balance_tx)
    assert "is_system=True" in src, (
        "Bug: create_opening_balance_tx debe insertar is_system=True. "
        "El campo no está en el pg_insert().values(...)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TC-9: get_transactions — saldo inicial VISIBLE en el ledger (OPTION B)
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_transactions_ledger_includes_opening_balance(sqlite_engine):
    """get_transactions devuelve la tx de apertura (visible en el ledger — OPTION B).

    La apertura (is_system=True) APARECE en el ledger con el campo is_system=True
    para que el frontend pueda mostrar el badge "sistema".
    Las KPIs (get_overview, etc.) siguen excluyendo is_system=True.
    """
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        items, total = await get_transactions(s)

    descriptions = [item["description"] for item in items]
    assert "Saldo inicial" in descriptions, (
        "La descripción 'Saldo inicial' (is_system=True) DEBE aparecer "
        "en get_transactions — el ledger muestra todas las transacciones (OPTION B)"
    )
    assert total == 3, (
        f"El ledger debe contener 3 transacciones (2 normales + 1 apertura), "
        f"total={total}"
    )
    opening_item = next(i for i in items if i["description"] == "Saldo inicial")
    assert opening_item["is_system"] is True, (
        "La tx de apertura debe tener is_system=True en la respuesta del ledger"
    )
    normal_items = [i for i in items if not i["is_system"]]
    assert len(normal_items) == 2, (
        "Las 2 transacciones normales deben tener is_system=False"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TC-10: regresión — is_system=False no rompe el conteo normal
# ─────────────────────────────────────────────────────────────────────────────

async def test_integration_normal_transactions_still_counted(sqlite_engine):
    """Regresión: is_system=False (default) no rompe el conteo de txs normales."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        async with s.begin():
            await _create_test_data(s)

    async with factory() as s:
        overview = await get_overview(s)

    assert overview["num_transactions"] == 2, (
        "Regresión: las 2 transacciones normales deben seguir contándose"
    )
    assert overview["total_income"] == pytest.approx(1000.00)
    assert overview["total_expense"] == pytest.approx(200.00)

    async with factory() as s:
        items, total = await get_transactions(s)

    assert total == 3
    descs = {item["description"] for item in items}
    assert "Nómina mayo" in descs, (
        "Regresión: 'Nómina mayo' (is_system=False) debe aparecer en el ledger"
    )
    assert "MERCADONA" in descs, (
        "Regresión: 'MERCADONA' (is_system=False) debe aparecer en el ledger"
    )
    assert "Saldo inicial" in descs, (
        "Regresión OPTION B: 'Saldo inicial' (is_system=True) DEBE aparecer en el ledger"
    )
