"""Modelo 720 detector: from January to March, whether the Fidelity shares held on the previous
December 31 exceeded the threshold, valued at that day's cached close, and the texts that tell it."""

from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from finlytics.db.models import (
    Base,
    EsppLot,
    InvestmentConnection,
    Notification,
    PriceHistory,
    User,
)
from finlytics.notifications.detectors import Modelo720Detector
from finlytics.notifications.messages import render_notification_text

# The last weekday of each quarter of 2026, when the ESPP buys.
MARCH, SEPTEMBER, DECEMBER = date(2026, 3, 31), date(2026, 9, 30), date(2026, 12, 31)
JANUARY = date(2027, 1, 15)
_hashes = itertools.count()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            User(id=1, username="owner", password_hash="-"),
            User(id=2, username="other", password_hash="-"),
        ])
        await session.commit()
        yield session
    await engine.dispose()


async def connect(db: AsyncSession, user_id: int = 1) -> int:
    conn = InvestmentConnection(user_id=user_id, plugin_id="fidelity-espp", status="active")
    db.add(conn)
    await db.commit()
    return conn.id


async def add_lot(
    db: AsyncSession, connection_id: int, purchased: date, shares: str, source: str = "SP"
) -> None:
    db.add(EsppLot(
        connection_id=connection_id, purchase_date=purchased, shares=Decimal(shares),
        cost_basis=Decimal(0), cost_basis_per_share=Decimal(0), source_currency="USD",
        share_source=source, dedup_hash=f"lot-{next(_hashes)}",
    ))
    await db.commit()


async def add_close(db: AsyncSession, day: date, close_eur: str) -> None:
    db.add(PriceHistory(
        ticker="MSFT", price_date=day, close_usd=Decimal(close_eur),
        fx_eur_usd=Decimal(1), close_eur=Decimal(close_eur),
    ))
    await db.commit()


async def holding(db: AsyncSession, *shares: tuple[date, str], user_id: int = 1) -> None:
    """A Fidelity account with these purchases, and prices up to the first trading day of 2027."""
    connection_id = await connect(db, user_id)
    for purchased, count in shares:
        await add_lot(db, connection_id, purchased, count)
    await add_close(db, date(2026, 12, 30), "390")
    await add_close(db, DECEMBER, "400")
    await add_close(db, date(2027, 1, 4), "999")


async def detect(db: AsyncSession, today: date = JANUARY, user_id: int = 1):
    return await Modelo720Detector().evaluate(db, user_id, today=today)


@pytest.mark.parametrize(
    ("december_shares", "verdict", "severity", "value"),
    [
        ("30.5", "exceeds", "warning", 52200.0),
        # Exactly the threshold does not exceed it.
        ("25", "below", "info", 50000.0),
        ("5", "below", "info", 42000.0),
    ],
)
async def test_tells_whether_the_shares_held_on_december_31_exceeded_the_threshold(
    db, december_shares: str, verdict: str, severity: str, value: float
) -> None:
    await holding(db, (SEPTEMBER, "100"), (DECEMBER, december_shares))

    (alert,) = await detect(db)

    # Valued at December 31's close, not at the later one.
    assert alert.source == "modelo720"
    assert alert.type == f"modelo720_{verdict}"
    assert alert.severity == severity
    assert alert.dedup_key == f"modelo720:2026:{verdict}"
    assert alert.title_key == alert.body_key == f"notif.modelo720_{verdict}"
    assert alert.title_args == {"year": "2026"}
    assert alert.body_args == {"value_eur": value}
    assert alert.action_link == "/investments/fidelity-espp"


async def test_counts_dividend_shares_and_ignores_those_bought_after_december_31(db) -> None:
    connection_id = await connect(db)
    await add_lot(db, connection_id, MARCH, "120")
    await add_lot(db, connection_id, date(2026, 6, 11), "1.5", source="DO")
    await add_lot(db, connection_id, date(2027, 3, 31), "500")
    await add_close(db, DECEMBER, "400")
    await add_close(db, date(2027, 1, 4), "400")

    (alert,) = await detect(db, date(2027, 3, 31))

    assert alert.body_args == {"value_eur": 48600.0}


@pytest.mark.parametrize("today", [date(2026, 12, 31), date(2027, 4, 1)])
async def test_says_nothing_outside_the_filing_window(db, today: date) -> None:
    await holding(db, (SEPTEMBER, "100"), (DECEMBER, "100"))
    assert await detect(db, today) == []


async def test_waits_until_a_later_close_proves_the_year_end_one_final(db) -> None:
    connection_id = await connect(db)
    await add_lot(db, connection_id, DECEMBER, "200")
    await add_close(db, DECEMBER, "400")

    assert await detect(db) == []

    await add_close(db, date(2027, 1, 4), "410")
    (alert,) = await detect(db)
    assert alert.body_args == {"value_eur": 80000.0}


async def test_waits_in_january_for_the_december_purchase_while_the_plan_buys(db) -> None:
    await holding(db, (SEPTEMBER, "120"))

    assert await detect(db) == []
    # From February on it tells what it has: the purchase may never come.
    (alert,) = await detect(db, date(2027, 2, 1))
    assert alert.dedup_key == "modelo720:2026:below"


async def test_does_not_wait_for_a_plan_that_stopped_buying(db) -> None:
    await holding(db, (MARCH, "200"))

    (alert,) = await detect(db)

    assert alert.dedup_key == "modelo720:2026:exceeds"


async def test_says_nothing_without_fidelity_shares_of_the_user(db) -> None:
    assert await detect(db) == []
    await holding(db, (SEPTEMBER, "100"), (DECEMBER, "100"), user_id=2)
    assert await detect(db) == []


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (
            "exceeds",
            (
                "⚠️ Modelo 720 (ejercicio 2026): tus acciones de Fidelity superaban el umbral "
                "a 31 de diciembre. El plazo acaba el 31 de marzo."
            ),
        ),
        (
            "below",
            (
                "ℹ️ Modelo 720 (ejercicio 2026): tus acciones de Fidelity no superaban el umbral "
                "a 31 de diciembre."
            ),
        ),
    ],
)
def test_telegram_tells_the_verdict_without_figures(verdict: str, expected: str) -> None:
    alert = Notification(
        title_key=f"notif.modelo720_{verdict}", title_args={"year": "2026"},
        body_args={"value_eur": 52200.0},
    )
    assert render_notification_text(alert) == expected
