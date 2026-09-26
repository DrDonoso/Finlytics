"""Statement ingestion, whose idempotency rests on ``INSERT ... ON CONFLICT``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from finlytics.db.models import ImportRun, Tag, Transaction, transaction_tags
from finlytics.db.repository import compute_dedup_hash, create_opening_balance_tx
from tests.pg.support import ingest, tx


async def stored(sessions: async_sessionmaker[AsyncSession]) -> list[Transaction]:
    async with sessions() as s:
        return list((await s.scalars(select(Transaction).order_by(Transaction.id))).all())


async def test_reimporting_a_statement_inserts_nothing(sessions, accounts):
    statement = [tx(), tx(description="LIDL"), tx(amount=Decimal(1500), description="NOMINA")]

    assert await ingest(sessions, accounts[0], statement) == (3, 0)
    assert await ingest(sessions, accounts[0], statement) == (0, 3)
    assert len(await stored(sessions)) == 3


async def test_a_line_repeated_within_one_statement_is_kept_once(sessions, accounts):
    assert await ingest(sessions, accounts[0], [tx(), tx()]) == (1, 1)


async def test_allow_duplicate_keeps_the_repeat(sessions, accounts):
    assert await ingest(sessions, accounts[0], [tx(), tx(allow_duplicate=True)]) == (2, 0)


async def test_the_same_movement_in_another_account_is_not_a_duplicate(sessions, accounts):
    assert await ingest(sessions, accounts[0], [tx()]) == (1, 0)
    assert await ingest(sessions, accounts[1], [tx()]) == (1, 0)


async def test_lines_differing_only_in_detail_are_both_kept(sessions, accounts):
    lines = [tx(detail="Recibo luz"), tx(detail="Recibo agua")]

    assert await ingest(sessions, accounts[0], lines) == (2, 0)


async def test_amount_spelling_does_not_defeat_the_duplicate_check(sessions, accounts):
    assert await ingest(sessions, accounts[0], [tx(amount=Decimal("-42.5"))]) == (1, 0)
    assert await ingest(sessions, accounts[0], [tx(amount=Decimal("-42.500"))]) == (0, 1)


@pytest.mark.parametrize("amount", ["10.005", "-10.005", "0.004", "-0.004"])
async def test_a_stored_row_reproduces_its_own_key(sessions, accounts, amount):
    """``Numeric(14, 2)`` rounds on insert, so the key must be the rounded amount's."""
    await ingest(sessions, accounts[0], [tx(amount=Decimal(amount))])

    [row] = await stored(sessions)
    assert row.dedup_hash == compute_dedup_hash(
        row.account_id, row.transaction_date, row.amount, row.description, row.detail
    )


async def test_tags_are_linked_only_to_inserted_rows(sessions, accounts):
    await ingest(sessions, accounts[0], [tx(tags=["Luz"])])
    await ingest(sessions, accounts[0], [tx(tags=["agua"])])

    async with sessions() as s:
        tags = (await s.scalars(select(Tag.name))).all()
        links = await s.scalar(select(func.count()).select_from(transaction_tags))
    assert tags == ["luz"]
    assert links == 1


async def test_the_opening_balance_is_written_once(sessions, accounts):
    for _ in range(2):
        async with sessions() as s, s.begin():
            await create_opening_balance_tx(s, accounts[0], "EUR", 1234.56, date(2025, 1, 1))

    rows = await stored(sessions)
    assert [(r.description, r.amount, r.balance_after, r.is_system) for r in rows] == [
        ("Saldo inicial", Decimal("1234.56"), Decimal("1234.56"), True)
    ]
    async with sessions() as s:
        runs = (
            await s.execute(
                select(ImportRun.num_inserted, ImportRun.num_duplicates).order_by(ImportRun.id)
            )
        ).all()
    assert [tuple(r) for r in runs] == [(1, 0), (0, 1)]
