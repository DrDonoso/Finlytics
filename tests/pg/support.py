"""Helpers shared by the PostgreSQL tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from finlytics.contracts import ExtractedTransaction
from finlytics.db.models import ImportRun
from finlytics.db.repository import upsert_transactions

REPO = Path(__file__).resolve().parents[2]


def tx(**overrides: Any) -> ExtractedTransaction:
    """A statement line; any field can be overridden."""
    fields: dict[str, Any] = {
        "transaction_date": date(2025, 3, 14),
        "amount": Decimal("-42.50"),
        "description": "MERCADONA",
        "category": "Groceries",
        "account_ref": "BBVA",
    }
    return ExtractedTransaction(**(fields | overrides))


async def ingest(
    sessions: async_sessionmaker[AsyncSession],
    account_id: int,
    txs: list[ExtractedTransaction],
) -> tuple[int, int]:
    """Import ``txs`` into ``account_id`` the way a confirmed statement is."""
    async with sessions() as s, s.begin():
        run = ImportRun(account_id=account_id, source_filename="statement.pdf")
        s.add(run)
        await s.flush()
        return await upsert_transactions(s, run, txs)


def server_url() -> URL | None:
    """The server named by ``TEST_DATABASE_URL``, or None when it is unset."""
    raw = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not raw:
        return None
    url = make_url(raw)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+asyncpg")
    return url


def dsn(url: URL) -> str:
    """``url`` in the form asyncpg itself accepts."""
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


async def _admin(server: URL, statement: str) -> None:
    conn = await asyncpg.connect(dsn(server))
    try:
        await conn.execute(statement)
    finally:
        await conn.close()


async def create_database(server: URL, *, template: str | None = None) -> str:
    name = f"finlytics_test_{uuid.uuid4().hex[:12]}"
    clause = f' TEMPLATE "{template}"' if template else ""
    await _admin(server, f'CREATE DATABASE "{name}"{clause}')
    return name


async def drop_database(server: URL, name: str) -> None:
    await _admin(server, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def query(url: URL, statement: str, *args: Any) -> list[asyncpg.Record]:
    """Run one statement from a synchronous test and return its rows."""

    async def run() -> list[asyncpg.Record]:
        conn = await asyncpg.connect(dsn(url))
        try:
            return await conn.fetch(statement, *args)
        finally:
            await conn.close()

    return asyncio.run(run())


def run_alembic(url: URL, *args: str) -> str:
    """Run Alembic in a subprocess, as the container entrypoint does.

    In-process, ``env.py`` would call ``asyncio.run`` inside the test's event
    loop and reconfigure logging for the rest of the session. Returns the
    combined output, which is where the migrations log their warnings.
    """
    env = {
        **os.environ,
        "DATABASE_URL": url.render_as_string(hide_password=False),
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode:
        raise AssertionError(f"alembic {' '.join(args)} failed:\n{output}")
    return output
