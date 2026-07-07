from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import TransactionOut, TransactionPage, TransactionUpdate
from finlytics.db import queries
from finlytics.db.queries import DedupCollisionError

router = APIRouter(prefix="/transactions", tags=["transactions"])

_SORT_ALLOWLIST = {"date", "amount", "description", "merchant", "category", "account"}


@router.get("", response_model=TransactionPage)
async def list_transactions(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    account_id: int | None = Query(None),
    category_id: int | None = Query(None),
    tag: list[str] | None = Query(None),
    flow: Literal["expense", "income"] | None = Query(None),
    description: str | None = Query(None),
    amount_min: float | None = Query(None, ge=0),
    amount_max: float | None = Query(None, ge=0),
    merchant: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("date"),
    order: str = Query("desc"),
    session: AsyncSession = Depends(get_db),
) -> TransactionPage:
    # Coerce unknown values to safe defaults so the endpoint never 500s.
    sort_by = sort if sort in _SORT_ALLOWLIST else "date"
    sort_dir = order if order in {"asc", "desc"} else "desc"

    items, total = await queries.get_transactions(
        session,
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tag,
        flow=flow,
        description=description,
        amount_min=amount_min,
        amount_max=amount_max,
        merchant=merchant,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return TransactionPage(items=items, total=total, limit=limit, offset=offset)


@router.patch("/{transaction_id}", response_model=TransactionOut)
async def patch_transaction(
    transaction_id: int,
    body: TransactionUpdate,
    session: AsyncSession = Depends(get_db),
) -> TransactionOut:
    """Partially update a transaction's description, category, and/or amount.

    * 404 — transaction not found.
    * 409 — the new (amount, description) would collide with another transaction's
             dedup_hash (same natural key already exists on a different row).
    """
    try:
        result = await queries.update_transaction(
            session,
            transaction_id,
            description=body.description,
            amount=body.amount,
            category_name=body.category,
            tags=body.tags,
            merchant=body.merchant,
        )
    except DedupCollisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return result
