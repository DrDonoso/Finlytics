"""Summary aggregations: totals, by category, by month and cash flow."""

from __future__ import annotations

from datetime import date
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import Account, Category, Transaction
from finlytics.db.queries.types import (
    AccountSummaryRow,
    CashflowItem,
    CashflowSummary,
    CategorySummaryRow,
    DaySummaryRow,
    MerchantSummaryRow,
    MonthSummaryRow,
    OverviewSummary,
)

from finlytics.db.queries._filters import (
    _apply_filters,
    _expense_expr,
    _income_expr,
)


# ── Aggregation queries ───────────────────────────────────────────────────────

async def get_overview(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    description: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    merchant: str | None = None,
    day: date | None = None,
) -> OverviewSummary:
    stmt = _apply_filters(
        select(
            _expense_expr().label("total_expense"),
            _income_expr().label("total_income"),
            func.count(Transaction.id).label("num_transactions"),
        ).select_from(Transaction),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
        description=description,
        amount_min=amount_min,
        amount_max=amount_max,
        merchant=merchant,
        day=day,
    )
    row = (await session.execute(stmt)).one()
    total_expense = float(row.total_expense)
    total_income = float(row.total_income)

    # Top spending category within the same date/account/category/tag window
    top_stmt = _apply_filters(
        select(
            Category.name.label("name"),
            func.sum(-Transaction.amount).label("amount"),
        )
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount < 0)
        .group_by(Category.name)
        .order_by(func.sum(-Transaction.amount).desc())
        .limit(1),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
        description=description,
        amount_min=amount_min,
        amount_max=amount_max,
        merchant=merchant,
        day=day,
    )
    top_row = (await session.execute(top_stmt)).one_or_none()

    # Currency: specific account's currency, or EUR as default
    currency = "EUR"
    if account_id is not None:
        acc_currency = (
            await session.execute(
                select(Account.currency).where(Account.id == account_id)
            )
        ).scalar_one_or_none()
        if acc_currency:
            currency = acc_currency

    return {
        "total_expense": total_expense,
        "total_income": total_income,
        "net": total_income - total_expense,
        "num_transactions": row.num_transactions,
        "top_category": (
            {"name": top_row.name, "amount": float(top_row.amount)}
            if top_row else None
        ),
        "currency": currency,
    }


async def get_by_category(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    merchant: str | None = None,
    day: date | None = None,
) -> list[CategorySummaryRow]:
    """Expenses by category, sorted descending by magnitude."""
    stmt = _apply_filters(
        select(
            Category.id.label("category_id"),
            Category.name.label("category"),
            func.sum(-Transaction.amount).label("amount"),
            func.count(Transaction.id).label("count"),
        )
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount < 0)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(-Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        tags=tags,
        flow=flow,
        merchant=merchant,
        day=day,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"category_id": r.category_id, "category": r.category, "amount": float(r.amount), "count": r.count}
        for r in rows
    ]


async def get_by_merchant(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    category_id: int | None = None,
    day: date | None = None,
) -> list[MerchantSummaryRow]:
    """Expenses by merchant, sorted descending by magnitude."""
    stmt = _apply_filters(
        select(
            Transaction.merchant.label("merchant"),
            func.sum(-Transaction.amount).label("amount"),
            func.count(Transaction.id).label("count"),
        )
        .select_from(Transaction)
        .where(Transaction.amount < 0)
        .where(Transaction.merchant.is_not(None))
        .where(func.trim(Transaction.merchant) != "")
        .group_by(Transaction.merchant)
        .order_by(func.sum(-Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        tags=tags,
        flow=flow,
        category_id=category_id,
        day=day,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"merchant": r.merchant, "amount": float(r.amount), "count": r.count}
        for r in rows
    ]


async def get_by_month(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
) -> list[MonthSummaryRow]:
    """Expense / income / net grouped by calendar month (chronological)."""
    month_expr = func.to_char(Transaction.transaction_date, "YYYY-MM")
    stmt = _apply_filters(
        select(
            month_expr.label("month"),
            _expense_expr().label("expense"),
            _income_expr().label("income"),
        )
        .select_from(Transaction)
        .group_by(month_expr)
        .order_by(month_expr),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "month": r.month,
            "expense": float(r.expense),
            "income": float(r.income),
            "net": float(r.income) - float(r.expense),
        }
        for r in rows
    ]


async def get_by_day(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    merchant: str | None = None,
) -> list[DaySummaryRow]:
    """Expense / income / net grouped by calendar day (chronological)."""
    day_expr = func.to_char(Transaction.transaction_date, "YYYY-MM-DD")
    stmt = _apply_filters(
        select(
            day_expr.label("day"),
            _expense_expr().label("expense"),
            _income_expr().label("income"),
        )
        .select_from(Transaction)
        .group_by(day_expr)
        .order_by(day_expr),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
        merchant=merchant,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "day": r.day,
            "expense": float(r.expense),
            "income": float(r.income),
            "net": float(r.income) - float(r.expense),
        }
        for r in rows
    ]


async def get_by_account(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
) -> list[AccountSummaryRow]:
    """Expense / income / net grouped by account."""
    stmt = _apply_filters(
        select(
            Account.name.label("account"),
            Account.currency.label("currency"),
            _expense_expr().label("expense"),
            _income_expr().label("income"),
        )
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .group_by(Account.name, Account.currency),
        from_date=from_date,
        to_date=to_date,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "account": r.account,
            "expense": float(r.expense),
            "income": float(r.income),
            "net": float(r.income) - float(r.expense),
            "currency": r.currency,
        }
        for r in rows
    ]


# ── Cashflow aggregation ──────────────────────────────────────────────────────

async def get_cashflow(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
) -> CashflowSummary:
    """Income and expense totals per category, for a Sankey diagram.

    * ``income``  — list of ``{category, amount}`` where amount > 0, sorted desc.
    * ``expense`` — list of ``{category, amount}`` (positive magnitudes), sorted desc.
    * Transactions with no category_id are bucketed under ``"Other"``.
    """
    category_expr = func.coalesce(Category.name, "Other")

    income_stmt = _apply_filters(
        select(
            category_expr.label("category"),
            func.sum(Transaction.amount).label("amount"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount > 0)
        .group_by(category_expr)
        .order_by(func.sum(Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )

    expense_stmt = _apply_filters(
        select(
            category_expr.label("category"),
            func.sum(-Transaction.amount).label("amount"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount < 0)
        .group_by(category_expr)
        .order_by(func.sum(-Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )

    income_rows = (await session.execute(income_stmt)).all()
    expense_rows = (await session.execute(expense_stmt)).all()

    income: list[CashflowItem] = [
        {"category": r.category, "amount": float(r.amount)} for r in income_rows
    ]
    expense: list[CashflowItem] = [
        {"category": r.category, "amount": float(r.amount)} for r in expense_rows
    ]

    # Currency: specific account's currency, or EUR as default
    currency = "EUR"
    if account_id is not None:
        acc_currency = (
            await session.execute(
                select(Account.currency).where(Account.id == account_id)
            )
        ).scalar_one_or_none()
        if acc_currency:
            currency = acc_currency

    return {
        "income": income,
        "expense": expense,
        "total_income": sum(r["amount"] for r in income),
        "total_expense": sum(r["amount"] for r in expense),
        "currency": currency,
    }
