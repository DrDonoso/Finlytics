"""Summary / aggregation endpoints.

All monetary values in responses are positive magnitudes for expenses and
raw sums for income; ``net`` = income − expense.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import ByAccountRow, ByCategoryRow, ByDayRow, ByMerchantRow, ByMonthRow, CashflowOut, OverviewOut
from finlytics.db import queries

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("/overview", response_model=OverviewOut)
async def overview(
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
    day: date | None = Query(None, alias="day"),
    session: AsyncSession = Depends(get_db),
) -> OverviewOut:
    return await queries.get_overview(
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
        day=day,
    )


@router.get("/by-category", response_model=list[ByCategoryRow])
async def by_category(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    account_id: int | None = Query(None),
    tag: list[str] | None = Query(None),
    flow: Literal["expense", "income"] | None = Query(None),
    merchant: str | None = Query(None),
    day: date | None = Query(None, alias="day"),
    session: AsyncSession = Depends(get_db),
) -> list[ByCategoryRow]:
    return await queries.get_by_category(
        session, from_date=from_date, to_date=to_date, account_id=account_id, tags=tag, flow=flow,
        merchant=merchant, day=day,
    )


@router.get("/by-month", response_model=list[ByMonthRow])
async def by_month(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    account_id: int | None = Query(None),
    category_id: int | None = Query(None),
    tag: list[str] | None = Query(None),
    flow: Literal["expense", "income"] | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[ByMonthRow]:
    return await queries.get_by_month(
        session,
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tag,
        flow=flow,
    )


@router.get("/by-day", response_model=list[ByDayRow])
async def by_day(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    account_id: int | None = Query(None),
    category_id: int | None = Query(None),
    tag: list[str] | None = Query(None),
    flow: Literal["expense", "income"] | None = Query(None),
    merchant: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[ByDayRow]:
    return await queries.get_by_day(
        session,
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tag,
        flow=flow,
        merchant=merchant,
    )


@router.get("/by-merchant", response_model=list[ByMerchantRow])
async def by_merchant(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    account_id: int | None = Query(None),
    tag: list[str] | None = Query(None),
    flow: Literal["expense", "income"] | None = Query(None),
    category_id: int | None = Query(None),
    day: date | None = Query(None, alias="day"),
    session: AsyncSession = Depends(get_db),
) -> list[ByMerchantRow]:
    return await queries.get_by_merchant(
        session, from_date=from_date, to_date=to_date, account_id=account_id, tags=tag, flow=flow,
        category_id=category_id, day=day,
    )


@router.get("/by-account", response_model=list[ByAccountRow])
async def by_account(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    category_id: int | None = Query(None),
    tag: list[str] | None = Query(None),
    flow: Literal["expense", "income"] | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[ByAccountRow]:
    return await queries.get_by_account(
        session, from_date=from_date, to_date=to_date, category_id=category_id, tags=tag, flow=flow
    )


@router.get("/cashflow", response_model=CashflowOut)
async def cashflow(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    account_id: int | None = Query(None),
    category_id: int | None = Query(None),
    tag: list[str] | None = Query(None),
    flow: Literal["expense", "income"] | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> CashflowOut:
    """Income and expense per category for a Sankey diagram.

    Amounts are always positive magnitudes.  Transactions without a category
    are bucketed under ``"Other"``.  Use ``?tag=luz&tag=agua`` to drill down
    into multiple tags (OR semantics).
    """
    return await queries.get_cashflow(
        session, from_date=from_date, to_date=to_date, account_id=account_id, category_id=category_id, tags=tag, flow=flow
    )
