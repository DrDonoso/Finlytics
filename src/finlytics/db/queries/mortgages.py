"""Mortgage links and recorded charges shared by reconciliation and summaries."""

from datetime import date
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finlytics.db.models import EuriborRate, Mortgage, Transaction
from finlytics.db.queries.types import MortgageChargeRow

MORTGAGE_RELATIONS = (
    selectinload(Mortgage.rate_periods),
    selectinload(Mortgage.bonuses),
    selectinload(Mortgage.prepayments),
)


async def get_linked_mortgages(
    db: AsyncSession, user_id: int, account_id: int, *, limit: int
) -> list[Mortgage]:
    rows = await db.scalars(
        select(Mortgage).where(
            Mortgage.user_id == user_id,
            or_(
                Mortgage.linked_account_id == account_id,
                and_(
                    Mortgage.linked_account_id.is_(None),
                    Mortgage.linked_category_id.is_not(None),
                ),
            ),
        ).options(*MORTGAGE_RELATIONS).order_by(Mortgage.id).limit(limit)
    )
    return list(rows.all())


async def get_mortgage_charges(
    db: AsyncSession, *, account_id: int | None, category_id: int | None,
    since: date, through: date | None = None,
) -> list[MortgageChargeRow]:
    if account_id is None and category_id is None:
        return []
    stmt = select(
        Transaction.id, Transaction.account_id, Transaction.transaction_date, Transaction.amount,
    ).where(
        Transaction.transaction_date >= since,
        Transaction.amount < 0,
        Transaction.is_system.is_(False),
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    if through is not None:
        stmt = stmt.where(Transaction.transaction_date <= through)
    rows = (await db.execute(stmt.order_by(
        Transaction.transaction_date, -Transaction.amount, Transaction.id,
    ))).all()
    return [
        {"id": row.id, "account_id": row.account_id,
         "date": row.transaction_date, "amount": abs(row.amount)}
        for row in rows
    ]


async def get_cached_mortgage_index(
    db: AsyncSession, index_name: str
) -> dict[date, Decimal]:
    rows = await db.execute(
        select(EuriborRate.period, EuriborRate.rate)
        .where(EuriborRate.index_name == index_name).order_by(EuriborRate.period)
    )
    return {period: rate for period, rate in rows.all()}
