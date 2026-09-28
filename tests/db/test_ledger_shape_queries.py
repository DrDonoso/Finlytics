"""The ledger-shape queries the assistant reads its context from.

Both used to be inline SQL in the assistant. The investments one counted
``active`` connections only, so a user whose Indexa sync had failed was told
they held no investments while the page beside the chat still showed the card.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.db.models import Account, Base, ImportRun, InvestmentConnection, Transaction, User
from finlytics.db.queries import get_transaction_date_range, has_investment_connections


@pytest.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _tx(tx_id: int, day: date, *, is_system: bool = False) -> Transaction:
    return Transaction(
        id=tx_id,
        account_id=1,
        import_run_id=1,
        transaction_date=day,
        amount=Decimal("-10.00"),
        currency="EUR",
        description=f"TX {tx_id}",
        dedup_hash=f"hash-{tx_id}",
        is_system=is_system,
    )


async def _seed_ledger(factory, *rows: Transaction) -> None:
    async with factory() as s, s.begin():
        s.add(Account(id=1, name="BBVA", type="bank"))
        s.add(ImportRun(id=1, account_id=1, source_filename="a.pdf"))
        s.add_all(rows)


async def test_date_range_leaves_the_opening_balance_out(factory):
    await _seed_ledger(
        factory,
        _tx(1, date(2019, 1, 1), is_system=True),
        _tx(2, date(2024, 3, 5)),
        _tx(3, date(2026, 7, 30)),
    )

    async with factory() as s:
        bounds = await get_transaction_date_range(s)

    assert bounds == {"first": date(2024, 3, 5), "last": date(2026, 7, 30)}


async def test_empty_ledger_has_no_range(factory):
    await _seed_ledger(factory, _tx(1, date(2019, 1, 1), is_system=True))

    async with factory() as s:
        bounds = await get_transaction_date_range(s)

    assert bounds == {"first": None, "last": None}


@pytest.mark.parametrize(
    ("status", "expected"),
    [("active", True), ("error", True), ("disconnected", False)],
)
async def test_a_connection_that_holds_money_counts(factory, status, expected):
    async with factory() as s, s.begin():
        s.add_all([
            User(id=1, username="me", password_hash="x"),
            User(id=2, username="other", password_hash="x"),
        ])
        s.add_all([
            InvestmentConnection(user_id=1, plugin_id="indexa-capital", status=status),
            InvestmentConnection(user_id=2, plugin_id="indexa-capital", status="active"),
        ])

    async with factory() as s:
        assert await has_investment_connections(s, 1) is expected
