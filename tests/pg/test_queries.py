"""Aggregations that lean on PostgreSQL functions and operators."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finlytics.db.queries import get_by_day, get_by_month, get_transactions
from finlytics.db.repository import create_opening_balance_tx
from tests.pg.support import ingest, tx


@pytest.fixture
async def ledger(sessions, accounts):
    await ingest(
        sessions,
        accounts[0],
        [
            tx(transaction_date=date(2025, 1, 31), amount=Decimal("-10.25")),
            tx(transaction_date=date(2025, 1, 31), amount=Decimal("-4.75"), description="LIDL"),
            tx(transaction_date=date(2025, 2, 1), amount=Decimal(2000), description="NOMINA"),
            tx(transaction_date=date(2025, 2, 3), amount=Decimal(-60), description="DESCUENTO 50%"),
            tx(transaction_date=date(2025, 2, 3), amount=Decimal(-70), description="DESCUENTO 500"),
        ],
    )
    async with sessions() as s, s.begin():
        await create_opening_balance_tx(s, accounts[0], "EUR", 9999.99, date(2025, 1, 1))


async def test_months_are_grouped_without_the_opening_balance(sessions, ledger):
    async with sessions() as s:
        months = await get_by_month(s)

    assert months == [
        {"month": "2025-01", "expense": 15.0, "income": 0.0, "net": -15.0},
        {"month": "2025-02", "expense": 130.0, "income": 2000.0, "net": 1870.0},
    ]


async def test_days_are_grouped_without_the_opening_balance(sessions, ledger):
    async with sessions() as s:
        days = await get_by_day(s, from_date=date(2025, 1, 1), to_date=date(2025, 2, 1))

    assert days == [
        {"day": "2025-01-31", "expense": 15.0, "income": 0.0, "net": -15.0},
        {"day": "2025-02-01", "expense": 0.0, "income": 2000.0, "net": 2000.0},
    ]


async def test_a_percent_sign_in_the_search_is_a_literal(sessions, ledger):
    async with sessions() as s:
        items, total = await get_transactions(s, description="descuento 50%")

    assert total == 1
    assert [i["description"] for i in items] == ["DESCUENTO 50%"]
