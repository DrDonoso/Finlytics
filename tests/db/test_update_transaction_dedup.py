"""update_transaction must only re-key a row whose natural key actually changed.

The edit form resends description and amount on every save, so a category-only
edit of a forced duplicate — or of a row the 0024 migration parked under a
``legacy:`` key — used to recompute the natural hash, find its twin and 409.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.db.models import Account, Base, Category, ImportRun, Transaction
from finlytics.db.queries import DedupCollisionError, update_transaction
from finlytics.db.repository import compute_dedup_hash

_DATE = date(2024, 6, 1)
_TWIN_HASH = compute_dedup_hash(1, _DATE, Decimal("-42.50"), "MERCADONA", disambiguator="legacy:2")


def _natural(description: str) -> str:
    return compute_dedup_hash(1, _DATE, Decimal("-42.50"), description)


def _tx(tx_id: int, description: str, dedup_hash: str) -> Transaction:
    return Transaction(
        id=tx_id,
        account_id=1,
        import_run_id=1,
        transaction_date=_DATE,
        amount=Decimal("-42.50"),
        currency="EUR",
        description=description,
        dedup_hash=dedup_hash,
        is_system=False,
    )


@pytest.fixture
async def sessions():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s, s.begin():
        s.add(Account(id=1, name="BBVA", type="bank"))
        s.add(ImportRun(id=1, account_id=1, source_filename="a.pdf"))
        s.add(Category(name="Groceries", name_es="Supermercado", is_base=True))
        s.add_all([
            _tx(1, "MERCADONA", _natural("MERCADONA")),
            _tx(2, "MERCADONA", _TWIN_HASH),
            _tx(3, "LIDL", _natural("LIDL")),
        ])
    yield factory
    await engine.dispose()


async def _hash(factory, tx_id: int) -> str:
    async with factory() as s:
        return await s.scalar(select(Transaction.dedup_hash).where(Transaction.id == tx_id))


async def test_resaving_a_forced_duplicate_keeps_its_key(sessions):
    async with sessions() as s:
        row = await update_transaction(
            s, 2, description="MERCADONA", amount=-42.5, category_name="Groceries"
        )

    assert row is not None and row["category"] == "Groceries"
    assert await _hash(sessions, 2) == _TWIN_HASH


async def test_a_case_only_description_edit_keeps_a_forced_duplicates_key(sessions):
    async with sessions() as s:
        row = await update_transaction(s, 2, description="  Mercadona ", amount=-42.5)

    assert row is not None and row["description"] == "  Mercadona "
    assert await _hash(sessions, 2) == _TWIN_HASH


async def test_a_real_description_change_rekeys_to_the_natural_hash(sessions):
    async with sessions() as s:
        await update_transaction(s, 2, description="MERCADONA CENTRO", amount=-42.5)

    assert await _hash(sessions, 2) == _natural("MERCADONA CENTRO")


async def test_an_edit_onto_another_rows_key_is_rejected(sessions):
    async with sessions() as s:
        with pytest.raises(DedupCollisionError):
            await update_transaction(s, 3, description="MERCADONA", amount=-42.5)

    assert await _hash(sessions, 3) == _natural("LIDL")
