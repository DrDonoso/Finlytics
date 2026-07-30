"""Consultas de la vista mensual de extractos."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import Account, ImportRun, Transaction



# ── Statements (monthly view) ─────────────────────────────────────────────────

async def get_statement_months(
    session: AsyncSession,
    *,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return one entry per (year, month) that has ≥1 transaction, sorted DESC.

    When *account_id* is provided, restricts results to that account only.
    When omitted (``None``), all accounts are included (original behaviour).
    """
    year_col = func.extract("year", Transaction.transaction_date)
    month_col = func.extract("month", Transaction.transaction_date)
    stmt = (
        select(
            year_col.label("year"),
            month_col.label("month"),
            func.count(Transaction.id).label("count"),
        )
        .select_from(Transaction)
        .group_by(year_col, month_col)
        .order_by(year_col.desc(), month_col.desc())
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    rows = (await session.execute(stmt)).all()
    return [{"year": int(r.year), "month": int(r.month), "count": r.count} for r in rows]


async def delete_statement_month(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    account_id: int | None = None,
) -> int:
    """Hard-delete all transactions whose date falls within the given calendar month.

    When *account_id* is provided, only that account's transactions are deleted.
    When omitted (``None``), transactions for ALL accounts in the month are removed
    (original behaviour).

    The ``transaction_tags`` junction table is cleaned up automatically via the
    DB-level ``ON DELETE CASCADE`` on its ``transaction_id`` FK — no explicit
    junction delete is required.

    Returns the number of transactions deleted.
    """
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    stmt = delete(Transaction).where(
        Transaction.transaction_date >= first_day,
        Transaction.transaction_date <= last_day,
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    async with session.begin():
        result = await session.execute(stmt)
        return result.rowcount


async def get_statement_originals(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return ImportRuns that have an original PDF on disk for the given month.

    Filters by ``period == "YYYY-MM"`` and ``source_path IS NOT NULL``.
    Optionally restricts to a single account when *account_id* is provided.
    Returns DISTINCT by source_path — when multiple runs share a filename
    (overwrite semantics) the one with the highest id (latest) is returned.
    """
    period = f"{year}-{month:02d}"
    # Use a subquery to pick the latest import_run_id per source_path.
    inner = (
        select(
            func.max(ImportRun.id).label("run_id"),
        )
        .where(ImportRun.period == period)
        .where(ImportRun.source_path.is_not(None))
        .group_by(ImportRun.source_path)
    )
    if account_id is not None:
        inner = inner.where(ImportRun.account_id == account_id)
    inner = inner.subquery()

    stmt = (
        select(
            ImportRun.id.label("import_run_id"),
            ImportRun.source_path.label("source_filename"),
            Account.name.label("account_name"),
            ImportRun.imported_at,
        )
        .select_from(ImportRun)
        .join(Account, ImportRun.account_id == Account.id)
        .join(inner, ImportRun.id == inner.c.run_id)
        .order_by(ImportRun.imported_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "import_run_id": r.import_run_id,
            "source_filename": r.source_filename,
            "account_name": r.account_name,
            "imported_at": r.imported_at,
        }
        for r in rows
    ]
