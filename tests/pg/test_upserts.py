"""Market data and ESPP lots, written with ``INSERT ... ON CONFLICT`` upserts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from finlytics.db.models import EsppLot, EuriborRate, InvestmentConnection, PriceHistory, User
from finlytics.investments import market_data
from finlytics.investments.fidelity import FidelityESPPProvider
from finlytics.mortgage import euribor

D1, D2, D3 = date(2025, 3, 3), date(2025, 3, 7), date(2025, 3, 10)


async def test_a_resync_revises_published_euribor_rates(sessions, monkeypatch):
    feeds = iter(
        [
            [(date(2025, 1, 1), Decimal("2.525")), (date(2025, 2, 1), Decimal("2.407"))],
            [(date(2025, 2, 1), Decimal("2.41")), (date(2025, 3, 1), Decimal("2.398"))],
        ]
    )

    async def fetch(index_name):
        return next(feeds)

    monkeypatch.setattr(euribor, "fetch_ecb_series", fetch)
    for _ in range(2):
        async with sessions() as s:
            assert await euribor.sync_index(s) == 2

    async with sessions() as s:
        rates = (
            await s.execute(
                select(EuriborRate.period, EuriborRate.rate).order_by(EuriborRate.period)
            )
        ).all()
    assert [tuple(r) for r in rates] == [
        (date(2025, 1, 1), Decimal("2.525")),
        (date(2025, 2, 1), Decimal("2.41")),
        (date(2025, 3, 1), Decimal("2.398")),
    ]


async def prices(sessions) -> list[tuple]:
    async with sessions() as s:
        rows = (
            await s.execute(
                select(
                    PriceHistory.price_date,
                    PriceHistory.close_usd,
                    PriceHistory.fx_eur_usd,
                    PriceHistory.close_eur,
                ).order_by(PriceHistory.price_date)
            )
        ).all()
    return [tuple(r) for r in rows]


async def test_the_top_up_leaves_an_empty_history_to_the_backfill(sessions, monkeypatch):
    async def fetch(symbol, start=None):
        raise AssertionError("the top-up must not fetch before a backfill")

    monkeypatch.setattr(market_data, "_fetch_yahoo_history", fetch)
    async with sessions() as s:
        await market_data.topup_recent_prices(s)

    assert await prices(sessions) == []


async def test_the_backfill_keeps_rows_and_the_top_up_settles_them(sessions, monkeypatch):
    msft_close = 400.0

    async def backfill_feed(yahoo_sym, stooq_sym, yf_sym, start=None):
        if yahoo_sym == "EURUSD=X":
            return [{"date": D1, "close": 1.25}]
        return [{"date": D1, "close": msft_close}, {"date": D2, "close": msft_close + 10}]

    monkeypatch.setattr(market_data, "_fetch_with_fallback", backfill_feed)
    async with sessions() as s:
        assert await market_data.backfill_price_history(D1, s) == 2
    msft_close = 999.0
    async with sessions() as s:
        await market_data.backfill_price_history(D1, s)

    backfilled = [
        (D1, Decimal(400), Decimal("0.8"), Decimal(320)),
        (D2, Decimal(410), Decimal("0.8"), Decimal(328)),
    ]
    assert await prices(sessions) == backfilled

    async def topup_feed(symbol, start=None):
        if symbol == "EURUSD=X":
            return [{"date": D3, "close": 1.0}]
        return [{"date": D2, "close": 415.0}, {"date": D3, "close": 420.0}]

    monkeypatch.setattr(market_data, "_fetch_yahoo_history", topup_feed)
    async with sessions() as s:
        await market_data.topup_recent_prices(s)

    assert await prices(sessions) == [
        backfilled[0],
        (D2, Decimal(415), Decimal(1), Decimal(415)),
        (D3, Decimal(420), Decimal(1), Decimal(420)),
    ]


def lot(purchase_date: date, shares: str, price: str, *, source: str = "SP", ordinal: int = 0):
    return SimpleNamespace(
        purchase_date=purchase_date,
        grant_date=None,
        shares=Decimal(shares),
        cost_basis=(Decimal(shares) * Decimal(price)).quantize(Decimal("0.01")),
        cost_basis_per_share=Decimal(price),
        source_currency="USD",
        share_source=source,
        holding_period=None,
        dedup_ordinal=ordinal,
    )


@pytest.fixture
async def connection_id(sessions) -> int:
    async with sessions() as s, s.begin():
        user = User(username="owner", password_hash="not-a-real-hash")
        s.add(user)
        await s.flush()
        connection = InvestmentConnection(user_id=user.id, plugin_id="fidelity-espp")
        s.add(connection)
    return connection.id


async def test_espp_lots_are_imported_once(sessions, connection_id):
    provider = FidelityESPPProvider()

    async def upload(lots, file_hash):
        async with sessions() as s:
            return await provider.import_lots(connection_id, lots, "USD", file_hash, s)

    statement = [
        lot(date(2025, 3, 31), "1.52300000", "350.123456"),
        lot(date(2025, 3, 31), "0.01230000", "360", source="DO"),
        lot(date(2025, 3, 31), "0.01230000", "360", source="DO", ordinal=1),
    ]
    assert await upload(statement, "a" * 64) == (3, 0)
    assert await upload(statement, "a" * 64) == (0, 3)
    assert await upload([*statement, lot(date(2025, 6, 30), "1.2", "370")], "b" * 64) == (1, 3)

    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(EsppLot)) == 4
