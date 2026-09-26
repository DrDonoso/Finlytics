"""Fixtures for the tests that run against a real PostgreSQL.

The rest of the suite uses SQLite or mocks, and neither can execute what only
PostgreSQL accepts: ``INSERT ... ON CONFLICT``, ``to_char`` and the migration
chain itself. These tests need the server named by ``TEST_DATABASE_URL``. They
are skipped without one, except under CI, where a missing server fails the run
instead of quietly dropping the only coverage those paths have.

The chain is migrated once into a template database and every test gets its own
copy, so the code under test begins and commits transactions exactly as it does
in production.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from finlytics.db.models import Account, Category
from tests.pg.support import create_database, drop_database, run_alembic, server_url


@pytest.fixture(scope="session")
def pg_server() -> URL:
    url = server_url()
    if url is None:
        if os.environ.get("CI"):
            pytest.fail("TEST_DATABASE_URL is not set; CI must run the PostgreSQL tests")
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


@pytest.fixture(autouse=True)
def _requires_pg(pg_server: URL) -> None:
    """Applies the skip-or-fail rule to every test here, fixtures or not."""


@pytest.fixture(scope="session")
def migrated_template(pg_server: URL) -> Iterator[str]:
    name = asyncio.run(create_database(pg_server))
    try:
        run_alembic(pg_server.set(database=name), "upgrade", "head")
        yield name
    finally:
        asyncio.run(drop_database(pg_server, name))


@pytest.fixture
async def database(pg_server: URL, migrated_template: str) -> AsyncIterator[URL]:
    """A database at head that belongs to this test alone."""
    name = await create_database(pg_server, template=migrated_template)
    try:
        yield pg_server.set(database=name)
    finally:
        await drop_database(pg_server, name)


@pytest.fixture
def empty_database(pg_server: URL) -> Iterator[URL]:
    """A database without a schema, for tests that drive Alembic themselves."""
    name = asyncio.run(create_database(pg_server))
    try:
        yield pg_server.set(database=name)
    finally:
        asyncio.run(drop_database(pg_server, name))


@pytest.fixture
async def engine(database: URL) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database, poolclass=NullPool)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def accounts(sessions: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    """Two bank accounts and the category ``support.tx`` files lines under.

    The category must exist beforehand: a new name is sent to the LLM.
    """
    async with sessions() as s, s.begin():
        bbva, revolut = Account(name="BBVA", type="bank"), Account(name="Revolut", type="bank")
        s.add_all([Category(name="Groceries", is_base=True), bbva, revolut])
    return bbva.id, revolut.id
