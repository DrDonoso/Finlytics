"""Investment connections, as the rest of the app needs to see them."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import InvestmentConnection

# A connection in ``error`` could not be read on its last sync, but the money it
# tracks still exists: the overview keeps its card and marks the total partial.
# Anything that asks "does this user hold investments" has to count it too, or
# it contradicts the page.
HOLDING_STATUSES: tuple[str, ...] = ("active", "error")


async def has_investment_connections(session: AsyncSession, user_id: int) -> bool:
    """Whether the user has any connection that holds money."""
    count = await session.scalar(
        select(func.count())
        .select_from(InvestmentConnection)
        .where(
            InvestmentConnection.user_id == user_id,
            InvestmentConnection.status.in_(HOLDING_STATUSES),
        )
    )
    return bool(count)
