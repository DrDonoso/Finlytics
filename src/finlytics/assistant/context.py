"""Compact "what data exists" header injected into the system prompt.

Without it, almost every conversation opens with the same ``list_reference_data``
round-trip just to learn that "supermercado" maps to category 7 — a paid LLM call
spent on a lookup that costs one cheap query.  The header is deliberately small:
names and ids only, no amounts, so it stays a fixed cost regardless of how much
history the ledger holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db import queries

__all__ = ["FinancialContext", "build_context", "render_context"]

# Long tag lists are a tail of one-off labels; the head is what gets reused.
_MAX_TAGS = 40


@dataclass(frozen=True)
class FinancialContext:
    """The shape of the ledger, without any of its numbers."""

    today: date
    accounts: list[dict]
    categories: list[dict]
    tags: list[str]
    first_transaction: date | None
    last_transaction: date | None
    has_investments: bool


async def build_context(
    session: AsyncSession,
    *,
    user_id: int,
    today: date,
) -> FinancialContext:
    """Read the reference data the assistant needs to interpret a question."""
    accounts = await queries.get_accounts(session)
    categories = await queries.get_categories(session)
    tags = await queries.get_tags(session)
    bounds = await queries.get_transaction_date_range(session)
    # Counts a connection in ``error`` too: the overview still shows its card,
    # so telling the model there is nothing would contradict the page.
    has_investments = await queries.has_investment_connections(session, user_id)

    return FinancialContext(
        today=today,
        accounts=[
            {"id": a["id"], "name": a["name"], "currency": a["currency"]} for a in accounts
        ],
        categories=[{"id": c["id"], "name": c["name"]} for c in categories],
        tags=[t["name"] for t in tags][:_MAX_TAGS],
        first_transaction=bounds["first"],
        last_transaction=bounds["last"],
        has_investments=has_investments,
    )


def render_context(ctx: FinancialContext) -> str:
    """Render the context as the compact block that goes into the system prompt."""
    accounts = (
        "\n".join(
            f"  - id={a['id']} · {a['name']} ({a['currency']})" for a in ctx.accounts
        )
        or "  (none)"
    )
    categories = (
        "\n".join(f"  - id={c['id']} · {c['name']}" for c in ctx.categories) or "  (none)"
    )
    tags = ", ".join(ctx.tags) if ctx.tags else "(none)"

    if ctx.first_transaction and ctx.last_transaction:
        coverage = (
            f"{ctx.first_transaction.isoformat()} → {ctx.last_transaction.isoformat()}"
        )
    else:
        coverage = "no transactions imported yet"

    investments = (
        "The user has at least one investment connection."
        if ctx.has_investments
        else "The user has NO investment connections — get_investment_overview will be empty."
    )

    return (
        "## Ledger context\n"
        f"Today is {ctx.today.isoformat()}.\n"
        f"Transaction data covers: {coverage}.\n"
        f"{investments}\n\n"
        f"Accounts:\n{accounts}\n\n"
        f"Categories:\n{categories}\n\n"
        f"Existing tags: {tags}\n"
    )
