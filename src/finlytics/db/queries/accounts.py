"""Queries over accounts."""

from __future__ import annotations


from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import Account, ImportRun, Transaction
from finlytics.db.queries.types import AccountRow



# ── Account queries ───────────────────────────────────────────────────────────

async def get_accounts(session: AsyncSession) -> list[AccountRow]:
    stmt = (
        select(
            Account.id,
            Account.name,
            Account.type,
            Account.currency,
            Account.account_number,
            func.count(Transaction.id).label("tx_count"),
        )
        .select_from(Account)
        .outerjoin(Transaction, Transaction.account_id == Account.id)
        .group_by(Account.id, Account.name, Account.type, Account.currency, Account.account_number)
        .order_by(Account.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": r.id, "name": r.name, "type": r.type, "currency": r.currency,
            "tx_count": r.tx_count, "account_number": r.account_number,
        }
        for r in rows
    ]


async def get_account_by_id(session: AsyncSession, account_id: int) -> AccountRow | None:
    """Return a single account row with tx_count, or None if not found."""
    stmt = (
        select(
            Account.id,
            Account.name,
            Account.type,
            Account.currency,
            Account.account_number,
            func.count(Transaction.id).label("tx_count"),
        )
        .select_from(Account)
        .outerjoin(Transaction, Transaction.account_id == Account.id)
        .where(Account.id == account_id)
        .group_by(Account.id, Account.name, Account.type, Account.currency, Account.account_number)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    return {
        "id": row.id, "name": row.name, "type": row.type, "currency": row.currency,
        "tx_count": row.tx_count, "account_number": row.account_number,
    }


async def delete_account(session: AsyncSession, account_id: int) -> int | None:
    """Delete an account and all its transactions.

    Explicitly deletes transactions (which auto-cascades to transaction_tags
    via the DB-level ON DELETE CASCADE on transaction_tags.transaction_id),
    then import_runs, then the account — all in one transaction.

    Returns the number of transactions deleted, or ``None`` if the account
    does not exist.
    """
    async with session.begin():
        account = await session.get(Account, account_id)
        if account is None:
            return None
        tx_result = await session.execute(
            delete(Transaction).where(Transaction.account_id == account_id)
        )
        tx_count = tx_result.rowcount
        await session.execute(
            delete(ImportRun).where(ImportRun.account_id == account_id)
        )
        await session.delete(account)
    return tx_count
