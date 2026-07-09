from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import DeleteMonthResult, StatementMonth
from finlytics.db import queries

router = APIRouter(prefix="/statements", tags=["statements"])


@router.get("/months", response_model=list[StatementMonth])
async def list_statement_months(
    account_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all (year, month) pairs that contain ≥1 transaction, sorted DESC.

    Pass ``?account_id=<id>`` to restrict to one account; omit for all accounts.
    """
    return await queries.get_statement_months(session, account_id=account_id)


@router.delete("/month", response_model=DeleteMonthResult)
async def delete_statement_month(
    year: int = Query(..., ge=1900, le=2100),
    month: int = Query(..., ge=1, le=12),
    account_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> DeleteMonthResult:
    """Delete all transactions for a given calendar month.

    Pass ``?account_id=<id>`` to restrict deletion to one account; omit to
    delete transactions for ALL accounts in that month.

    Hard-deletes every transaction whose ``transaction_date`` falls within
    [year-month-01 .. last day of month].  Junction rows in ``transaction_tags``
    are removed automatically via DB-level CASCADE.  Returns the count of deleted
    transactions so the frontend can confirm the operation.
    """
    deleted = await queries.delete_statement_month(
        session, year=year, month=month, account_id=account_id
    )
    return DeleteMonthResult(deleted=deleted)
