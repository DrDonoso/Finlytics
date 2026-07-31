"""Read-only tool catalogue exposed to the finance assistant.

Every tool is a thin, typed wrapper over ``finlytics.db.queries`` — the same
aggregation code that renders the dashboards.  That is deliberate: it makes a
chat answer structurally incapable of disagreeing with the UI, and it means the
model never needs (and never gets) SQL access.

Nothing here writes.  Adding a write tool later is additive, but it would also
need a confirmation step in the UI, so this module keeps the read surface
closed on purpose.

Result size is capped before returning: an unbounded ``search_transactions``
over five years would otherwise consume the whole context window on its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.assistant import projections
from finlytics.db import queries
from finlytics.db.models import Transaction

log = logging.getLogger(__name__)

__all__ = [
    "ToolContext",
    "ToolError",
    "TOOLS",
    "execute_tool",
    "openai_tool_schemas",
]


class ToolError(Exception):
    """Raised when a tool cannot run with the arguments the model supplied.

    Surfaced back to the model as a tool result rather than aborting the turn:
    a bad date string should let it retry, not kill the conversation.
    """


@dataclass
class ToolContext:
    """Everything a tool executor needs, passed in rather than imported.

    ``background_tasks`` is threaded through from the request so the Indexa
    portfolio cache can still schedule its refresh — without it, asking the
    assistant about investments would silently stop the cache from ever
    updating.
    """

    session: AsyncSession
    user_id: int
    today: date
    max_rows: int = 100
    projection_rates: tuple[float, float, float] = (2.0, 5.0, 8.0)
    background_tasks: Any = None


@dataclass(frozen=True)
class Tool:
    """A single callable exposed to the model."""

    name: str
    description: str
    parameters: dict
    executor: Callable[[dict, ToolContext], Awaitable[dict]]
    # Short, human-readable label the UI shows while the tool runs.
    label: str = ""


# ── Shared argument fragments ────────────────────────────────────────────────

_DATE_RANGE_PROPS = {
    "from_date": {
        "type": "string",
        "description": "Start of the period, inclusive, as YYYY-MM-DD. Omit for no lower bound.",
    },
    "to_date": {
        "type": "string",
        "description": "End of the period, inclusive, as YYYY-MM-DD. Omit for no upper bound.",
    },
}

_SCOPE_PROPS = {
    "account_id": {
        "type": "integer",
        "description": "Restrict to one account. Get ids from list_reference_data.",
    },
    "category_id": {
        "type": "integer",
        "description": "Restrict to one category. Get ids from list_reference_data.",
    },
    "tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Restrict to transactions carrying any of these tag names (OR).",
    },
}


# ── Argument coercion ────────────────────────────────────────────────────────

def _parse_date(value: Any, field_name: str) -> date | None:
    """Parse an ISO date, tolerating the ``YYYY-MM`` the model often emits."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        # "2026-03" is a month, not a day: read it as the first of that month
        # rather than rejecting it, because models produce it constantly.
        if len(text) == 7 and text[4] == "-":
            return date.fromisoformat(f"{text}-01")
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ToolError(
            f"{field_name} must be a date in YYYY-MM-DD format (got {value!r})."
        ) from exc


def _opt_int(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{field_name} must be an integer (got {value!r}).") from exc


def _opt_float(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{field_name} must be a number (got {value!r}).") from exc


def _opt_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _opt_flow(value: Any) -> str | None:
    text = _opt_str(value)
    if text is None:
        return None
    if text not in {"expense", "income"}:
        raise ToolError("flow must be either 'expense' or 'income'.")
    return text


def _opt_tags(value: Any) -> list[str] | None:
    if not value:
        return None
    if isinstance(value, str):
        value = [value]
    tags = [str(v).strip() for v in value if str(v).strip()]
    return tags or None


def _truncate(rows: list, ctx: ToolContext) -> tuple[list, bool]:
    """Cap a row list, reporting whether anything was dropped.

    The flag matters more than the cap: a silently shortened list would let the
    model state a total that is missing rows it never saw.
    """
    if len(rows) <= ctx.max_rows:
        return rows, False
    return rows[: ctx.max_rows], True


def _common_filters(args: dict) -> dict:
    """Extract the filter set shared by most aggregation tools."""
    return {
        "from_date": _parse_date(args.get("from_date"), "from_date"),
        "to_date": _parse_date(args.get("to_date"), "to_date"),
        "account_id": _opt_int(args.get("account_id"), "account_id"),
        "tags": _opt_tags(args.get("tags")),
        "flow": _opt_flow(args.get("flow")),
    }


# ── Executors ────────────────────────────────────────────────────────────────

async def _list_reference_data(args: dict, ctx: ToolContext) -> dict:
    accounts = await queries.get_accounts(ctx.session)
    categories = await queries.get_categories(ctx.session)
    tags = await queries.get_tags(ctx.session)

    bounds = (
        await ctx.session.execute(
            select(
                func.min(Transaction.transaction_date),
                func.max(Transaction.transaction_date),
            ).where(Transaction.is_system.is_(False))
        )
    ).one()

    return {
        "today": ctx.today.isoformat(),
        "accounts": [
            {"id": a["id"], "name": a["name"], "currency": a.get("currency")}
            for a in accounts
        ],
        "categories": [{"id": c["id"], "name": c["name"]} for c in categories],
        "tags": [t["name"] for t in tags][: ctx.max_rows],
        "data_range": {
            "first_transaction": bounds[0].isoformat() if bounds[0] else None,
            "last_transaction": bounds[1].isoformat() if bounds[1] else None,
        },
    }


async def _get_spending_summary(args: dict, ctx: ToolContext) -> dict:
    result = await queries.get_overview(
        ctx.session,
        **_common_filters(args),
        category_id=_opt_int(args.get("category_id"), "category_id"),
        merchant=_opt_str(args.get("merchant")),
    )
    return dict(result)


async def _get_spending_by_category(args: dict, ctx: ToolContext) -> dict:
    rows = await queries.get_by_category(
        ctx.session,
        **_common_filters(args),
        merchant=_opt_str(args.get("merchant")),
    )
    kept, truncated = _truncate(rows, ctx)
    return {"categories": kept, "truncated": truncated, "total_categories": len(rows)}


async def _get_spending_by_month(args: dict, ctx: ToolContext) -> dict:
    rows = await queries.get_by_month(
        ctx.session,
        **_common_filters(args),
        category_id=_opt_int(args.get("category_id"), "category_id"),
    )
    kept, truncated = _truncate(rows, ctx)
    return {"months": kept, "truncated": truncated, "total_months": len(rows)}


async def _get_spending_by_merchant(args: dict, ctx: ToolContext) -> dict:
    rows = await queries.get_by_merchant(
        ctx.session,
        **_common_filters(args),
        category_id=_opt_int(args.get("category_id"), "category_id"),
    )
    kept, truncated = _truncate(rows, ctx)
    return {"merchants": kept, "truncated": truncated, "total_merchants": len(rows)}


async def _get_cashflow(args: dict, ctx: ToolContext) -> dict:
    result = await queries.get_cashflow(
        ctx.session,
        **_common_filters(args),
        category_id=_opt_int(args.get("category_id"), "category_id"),
    )
    return dict(result)


async def _search_transactions(args: dict, ctx: ToolContext) -> dict:
    limit = _opt_int(args.get("limit"), "limit") or 25
    limit = max(1, min(limit, ctx.max_rows))

    items, total = await queries.get_transactions(
        ctx.session,
        **_common_filters(args),
        category_id=_opt_int(args.get("category_id"), "category_id"),
        description=_opt_str(args.get("description")),
        merchant=_opt_str(args.get("merchant")),
        amount_min=_opt_float(args.get("amount_min"), "amount_min"),
        amount_max=_opt_float(args.get("amount_max"), "amount_max"),
        limit=limit,
        offset=0,
        sort_by="date",
        sort_dir="desc",
    )

    # The full row carries balance_after, confidence and ids the model has no
    # use for; sending them would spend context on noise.
    slim = [
        {
            "date": it["transaction_date"],
            "description": it["description"],
            "merchant": it["merchant"],
            "amount": it["amount"],
            "currency": it["currency"],
            "category": it["category"],
            "account": it["account"],
            "tags": it["tags"],
        }
        for it in items
        # Opening-balance rows are synthetic; quoting one back as a real
        # transaction would be wrong, and the aggregations already exclude them.
        if not it["is_system"]
    ]
    return {"transactions": slim, "returned": len(slim), "total_matching": total}


async def _compare_periods(args: dict, ctx: ToolContext) -> dict:
    a_from = _parse_date(args.get("period_a_from"), "period_a_from")
    a_to = _parse_date(args.get("period_a_to"), "period_a_to")
    b_from = _parse_date(args.get("period_b_from"), "period_b_from")
    b_to = _parse_date(args.get("period_b_to"), "period_b_to")
    if not (a_from and a_to and b_from and b_to):
        raise ToolError(
            "compare_periods needs all four bounds: period_a_from, period_a_to, "
            "period_b_from and period_b_to."
        )

    account_id = _opt_int(args.get("account_id"), "account_id")

    rows_a = await queries.get_by_category(
        ctx.session, from_date=a_from, to_date=a_to, account_id=account_id
    )
    rows_b = await queries.get_by_category(
        ctx.session, from_date=b_from, to_date=b_to, account_id=account_id
    )

    by_a = {r["category"]: float(r["amount"]) for r in rows_a}
    by_b = {r["category"]: float(r["amount"]) for r in rows_b}

    changes = []
    for name in sorted(set(by_a) | set(by_b)):
        amount_a = by_a.get(name, 0.0)
        amount_b = by_b.get(name, 0.0)
        delta = amount_b - amount_a
        # A category that appears only in period B has no baseline, so a
        # percentage would be infinite — report it as null and let the model
        # describe it as new spending instead.
        pct = round(delta / amount_a * 100.0, 2) if amount_a > 0 else None
        changes.append(
            {
                "category": name,
                "period_a": round(amount_a, 2),
                "period_b": round(amount_b, 2),
                "delta": round(delta, 2),
                "delta_pct": pct,
            }
        )

    changes.sort(key=lambda c: abs(c["delta"]), reverse=True)
    kept, truncated = _truncate(changes, ctx)

    return {
        "period_a": {"from": a_from.isoformat(), "to": a_to.isoformat(), "total": round(sum(by_a.values()), 2)},
        "period_b": {"from": b_from.isoformat(), "to": b_to.isoformat(), "total": round(sum(by_b.values()), 2)},
        "changes": kept,
        "truncated": truncated,
    }


async def _get_investment_overview(args: dict, ctx: ToolContext) -> dict:
    # Imported lazily: the investments package pulls in the market-data stack,
    # and most conversations never touch it.
    from fastapi import BackgroundTasks

    from finlytics.api.investments import combined_overview

    overview = await combined_overview(
        background_tasks=ctx.background_tasks or BackgroundTasks(),
        user=_UserRef(ctx.user_id),
        db=ctx.session,
    )
    data = overview.model_dump()
    # Percentages here are already percentages (25.4 = 25.4%), unlike the
    # InvestmentPortfolio shape which uses fractions. Say so, or the model will
    # helpfully multiply by 100.
    data["_units"] = "All *_pct fields are percentages (25.4 means 25.4%). Amounts are EUR."
    return data


class _UserRef:
    """Minimal stand-in for the User the investments endpoint only reads ``id`` from."""

    __slots__ = ("id",)

    def __init__(self, user_id: int) -> None:
        self.id = user_id


async def _project_investment(args: dict, ctx: ToolContext) -> dict:
    try:
        result = projections.project(
            initial_amount=_opt_float(args.get("initial_amount"), "initial_amount") or 0.0,
            monthly_contribution=(
                _opt_float(args.get("monthly_contribution"), "monthly_contribution") or 0.0
            ),
            years=_opt_int(args.get("years"), "years") or 10,
            rates=ctx.projection_rates,
            annual_return_pct=_opt_float(args.get("annual_return_pct"), "annual_return_pct"),
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return projections.to_dict(result)


# ── Registry ─────────────────────────────────────────────────────────────────

def _tool(
    name: str,
    label: str,
    description: str,
    properties: dict,
    executor: Callable[[dict, ToolContext], Awaitable[dict]],
    required: list[str] | None = None,
) -> Tool:
    return Tool(
        name=name,
        label=label,
        description=description,
        parameters={
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
        executor=executor,
    )


_REGISTRY: list[Tool] = [
    _tool(
        "list_reference_data",
        "Reading accounts and categories",
        "List the accounts, categories and tags that exist, plus the date range "
        "covered by the ledger. Call this first whenever you need an account_id "
        "or category_id — never guess one.",
        {},
        _list_reference_data,
    ),
    _tool(
        "get_spending_summary",
        "Calculating totals",
        "Headline totals for a period: total expense, total income, net, "
        "transaction count and the single largest spending category.",
        {**_DATE_RANGE_PROPS, **_SCOPE_PROPS,
         "flow": {"type": "string", "enum": ["expense", "income"]},
         "merchant": {"type": "string", "description": "Restrict to one merchant name."}},
        _get_spending_summary,
    ),
    _tool(
        "get_spending_by_category",
        "Breaking down by category",
        "Expense totals grouped by category for a period, largest first. "
        "Amounts are positive magnitudes.",
        {**_DATE_RANGE_PROPS,
         "account_id": _SCOPE_PROPS["account_id"],
         "tags": _SCOPE_PROPS["tags"],
         "merchant": {"type": "string", "description": "Restrict to one merchant name."}},
        _get_spending_by_category,
    ),
    _tool(
        "get_spending_by_month",
        "Building the monthly trend",
        "Expense, income and net grouped by calendar month, chronological. Use "
        "this for trends, averages and 'how has X evolved' questions.",
        {**_DATE_RANGE_PROPS, **_SCOPE_PROPS,
         "flow": {"type": "string", "enum": ["expense", "income"]}},
        _get_spending_by_month,
    ),
    _tool(
        "get_spending_by_merchant",
        "Ranking merchants",
        "Expense totals grouped by merchant for a period, largest first. Use "
        "this to find recurring subscriptions and the biggest vendors.",
        {**_DATE_RANGE_PROPS, **_SCOPE_PROPS},
        _get_spending_by_merchant,
    ),
    _tool(
        "get_cashflow",
        "Analysing cash flow",
        "Income and expense totals per category side by side, for cash-flow and "
        "savings-rate questions.",
        {**_DATE_RANGE_PROPS, **_SCOPE_PROPS},
        _get_cashflow,
    ),
    _tool(
        "search_transactions",
        "Searching transactions",
        "Individual transactions matching a filter, newest first. Use it to cite "
        "concrete examples — not to add up totals, which the aggregation tools "
        "do exactly and cheaply.",
        {**_DATE_RANGE_PROPS, **_SCOPE_PROPS,
         "description": {"type": "string", "description": "Case-insensitive substring of the description."},
         "merchant": {"type": "string"},
         "flow": {"type": "string", "enum": ["expense", "income"]},
         "amount_min": {"type": "number", "description": "Minimum absolute amount."},
         "amount_max": {"type": "number", "description": "Maximum absolute amount."},
         "limit": {"type": "integer", "description": "How many rows to return (default 25)."}},
        _search_transactions,
    ),
    _tool(
        "compare_periods",
        "Comparing periods",
        "Per-category spending difference between two periods, biggest movement "
        "first. This is the tool for 'where could I cut back' and 'am I spending "
        "more than before' questions.",
        {"period_a_from": {"type": "string", "description": "Baseline period start, YYYY-MM-DD."},
         "period_a_to": {"type": "string", "description": "Baseline period end, YYYY-MM-DD."},
         "period_b_from": {"type": "string", "description": "Comparison period start, YYYY-MM-DD."},
         "period_b_to": {"type": "string", "description": "Comparison period end, YYYY-MM-DD."},
         "account_id": _SCOPE_PROPS["account_id"]},
        _compare_periods,
        required=["period_a_from", "period_a_to", "period_b_from", "period_b_to"],
    ),
    _tool(
        "get_investment_overview",
        "Reading the portfolio",
        "Current investment portfolio across all connected providers: total "
        "value, amount invested, gain/loss and allocation by provider and asset "
        "class.",
        {},
        _get_investment_overview,
    ),
    _tool(
        "project_investment",
        "Projecting returns",
        "Project a lump sum and/or a monthly contribution forward using compound "
        "interest, under conservative, base and optimistic return assumptions. "
        "ALWAYS use this instead of doing the arithmetic yourself. Only pass "
        "annual_return_pct when the user states an expected return explicitly.",
        {"initial_amount": {"type": "number", "description": "Lump sum invested today, in EUR."},
         "monthly_contribution": {"type": "number", "description": "Amount added every month, in EUR."},
         "years": {"type": "integer", "description": "Horizon in years (1-60)."},
         "annual_return_pct": {
             "type": "number",
             "description": "Only when the user gives an explicit expected annual return, e.g. 7 for 7%.",
         }},
        _project_investment,
        required=["years"],
    ),
]

TOOLS: dict[str, Tool] = {t.name: t for t in _REGISTRY}


def openai_tool_schemas() -> list[dict]:
    """Return the tool catalogue in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in _REGISTRY
    ]


async def execute_tool(name: str, args: dict, ctx: ToolContext) -> dict:
    """Run a tool, returning a JSON-serialisable result.

    Failures come back as ``{"error": ...}`` rather than raising: the model can
    correct a bad argument and retry, whereas an exception would end the turn
    and leave the user with nothing.

    ``ToolError`` text is our own validation wording, so it is safe to hand back
    and is what lets the model self-correct. An unexpected exception is not:
    a SQLAlchemy failure carries SQL and connection details, and the model is
    free to quote its tool results back to the user, so it stays in the log.
    """
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool {name!r}."}

    try:
        return await tool.executor(args or {}, ctx)
    except ToolError as exc:
        return {"error": str(exc)}
    except Exception:  # noqa: BLE001 — a broken tool must not kill the chat
        log.exception("Assistant tool %s failed", name)
        return {"error": f"The {name} query failed. Do not retry it this turn."}
