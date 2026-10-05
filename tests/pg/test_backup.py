"""A backup restored into another instance, through the API.

The API suite mocks the session, so the restore's ``INSERT ... ON CONFLICT``
statements and the export's joins only ever execute here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.db.models import InvestmentConnection, PriceHistory, Rule, User
from finlytics.db.repository import create_opening_balance_tx
from finlytics.investments.fidelity import FidelityESPPProvider
from tests.pg.support import create_database, drop_database, ingest, tx

Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
async def target(pg_server: URL, migrated_template: str) -> AsyncIterator[Sessions]:
    """A second, empty instance to restore into."""
    name = await create_database(pg_server, template=migrated_template)
    engine = create_async_engine(pg_server.set(database=name), poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        await drop_database(pg_server, name)


async def owner(sessions: Sessions) -> User:
    async with sessions() as s, s.begin():
        user = User(username="owner", password_hash="not-a-real-hash")
        s.add(user)
    return user


@asynccontextmanager
async def api(sessions: Sessions, user: User) -> AsyncIterator[AsyncClient]:
    async def db() -> AsyncIterator[AsyncSession]:
        async with sessions() as s:
            yield s

    async def current_user() -> User:
        return user

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = current_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def seed(sessions: Sessions, accounts: tuple[int, int]) -> User:
    """Something in every section of the backup; returns the owner."""
    bbva, revolut = accounts
    user = await owner(sessions)
    await ingest(
        sessions,
        bbva,
        [
            tx(tags=["super", "hogar"], category_confidence=0.92),
            tx(description="LIDL", amount=Decimal("-12.30")),
            tx(description="NOMINA", amount=Decimal("2150.00"), balance_after=Decimal("3200.55")),
            tx(description="OCTOPUS", amount=Decimal("-60.00"), detail="GCREOCTOPUSENERGY"),
            tx(description="OCTOPUS", amount=Decimal("-60.00"), detail="GCREOCTOPUSGAS"),
            tx(description="LIDL", amount=Decimal("-12.30"), allow_duplicate=True),
        ],
    )
    await ingest(sessions, revolut, [tx(account_ref="Revolut", merchant="Mercadona")])
    async with sessions() as s, s.begin():
        await create_opening_balance_tx(s, bbva, "EUR", 1000.0, date(2025, 3, 1))
        s.add(
            Rule(
                name="Lidl",
                priority=10,
                description_mode="contains",
                description_value="LIDL",
                amount_min=Decimal("1.50"),
                set_category="Groceries",
                add_tags=["super"],
            )
        )
        s.add(
            PriceHistory(
                ticker="MSFT",
                price_date=date(2025, 3, 31),
                close_usd=Decimal("375.39"),
                fx_eur_usd=Decimal("0.924931"),
                close_eur=Decimal("347.210342"),
            )
        )
        connection = InvestmentConnection(user_id=user.id, plugin_id="fidelity-espp")
        s.add(connection)
    lot = SimpleNamespace(
        purchase_date=date(2025, 3, 31),
        grant_date=date(2025, 1, 1),
        shares=Decimal("1.52300000"),
        cost_basis=Decimal("533.24"),
        cost_basis_per_share=Decimal("350.123456"),
        source_currency="USD",
        share_source="SP",
        holding_period="Short Term",
        dedup_ordinal=0,
    )
    async with sessions() as s:
        await FidelityESPPProvider().import_lots(connection.id, [lot], "USD", "c" * 64, s)
    return user


def nonzero(summary: dict[str, int]) -> dict[str, int]:
    return {k: v for k, v in summary.items() if v}


def comparable(document: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in document.items() if k != "exported_at"}


async def test_a_restored_backup_exports_the_same_data(sessions, accounts, target):
    async with api(sessions, await seed(sessions, accounts)) as client:
        backup = (await client.get("/api/backup/export")).json()

    async with api(target, await owner(target)) as client:
        first = await client.post("/api/backup/import", json=backup)
        again = await client.post("/api/backup/import", json=backup)
        restored = (await client.get("/api/backup/export")).json()

    assert first.status_code == again.status_code == 200
    assert nonzero(first.json()) == {
        "accounts_created": 2,
        "categories_created": 1,
        "tags_created": 2,
        "transactions_inserted": 8,
        "rules_created": 1,
        "investment_connections_created": 1,
        "espp_lots_inserted": 1,
        "price_history_inserted": 1,
    }
    assert nonzero(again.json()) == {
        "accounts_existing": 2,
        "categories_updated": 1,
        "tags_updated": 2,
        "transactions_duplicates": 8,
        "rules_updated": 1,
        "investment_connections_updated": 1,
        "espp_lots_duplicates": 1,
        "price_history_duplicates": 1,
    }

    txs = backup["transactions"]
    assert sorted(t["tags"] for t in txs) == [[]] * 7 + [["hogar", "super"]]
    assert sorted(t["detail"] for t in txs if t["detail"]) == [
        "GCREOCTOPUSENERGY",
        "GCREOCTOPUSGAS",
    ]
    assert [t["description"] for t in txs if t["is_system"]] == ["Saldo inicial"]
    assert [t["description"] for t in txs if t["duplicate_key"]] == ["LIDL"]
    assert comparable(restored) == comparable(backup)


async def test_restoring_a_backup_into_its_own_instance_inserts_nothing(sessions, accounts):
    async with api(sessions, await seed(sessions, accounts)) as client:
        backup = (await client.get("/api/backup/export")).json()
        summary = (await client.post("/api/backup/import", json=backup)).json()
        after = (await client.get("/api/backup/export")).json()

    assert summary["transactions_inserted"] == 0
    assert summary["transactions_duplicates"] == len(backup["transactions"]) == 8
    assert comparable(after) == comparable(backup)
