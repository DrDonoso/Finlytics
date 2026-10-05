"""Per-user assistant settings, token accounting and limit enforcement.

The cost guards below are fixed, not configurable from the environment: they
are the shape of the feature (one message is one to three paid LLM calls), and
what a self-hosted owner actually wants to tune — the message rate limit, the
monthly token budget, the system prompt — is editable in Settings → Assistant
and stored per user.

Two different guards live here and they do different jobs:

* the **message rate limit** is an in-memory sliding window. It stops a burst,
  and it resets on every restart.
* the **monthly token budget** is counted in the database. That is the only one
  that can actually cap spend, precisely because it survives a restart — an
  in-memory counter would hand back a full allowance every time the container
  came up, which for a monthly budget is the same as having no budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.assistant.prompts import (
    CONTEXT_PLACEHOLDER,
    DEFAULT_SYSTEM_PROMPT,
    MAX_CUSTOM_INSTRUCTIONS_CHARS,
    MAX_SYSTEM_PROMPT_CHARS,
    missing_safety_markers,
)
from finlytics.db.models import AssistantSettings, AssistantUsage, ImportSummaryAttempt

log = logging.getLogger(__name__)

# ── Cost guards ──────────────────────────────────────────────────────────────
# Hard stop on the tool-call loop. Every iteration is a paid LLM round-trip, and
# a model that keeps asking for one more query would otherwise bill indefinitely
# for a single user message.
MAX_TOOL_ITERATIONS = 5
# Past turns replayed as context. Older ones are dropped: the cost of a message
# grows with the length of the thread otherwise.
HISTORY_MESSAGES = 20
# Longest user message accepted, in characters.
MAX_MESSAGE_CHARS = 4000
# Rows any single tool may return before truncation. A multi-year transaction
# search would otherwise blow the context window on its own.
MAX_TOOL_RESULT_ROWS = 100
# Conversations kept per user; creating beyond this is rejected.
MAX_CONVERSATIONS = 100
# Messages per user per window, unless overridden in Settings → Assistant.
DEFAULT_RATE_LIMIT_MESSAGES = 30
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 3600
# Annual real-return assumptions (%) for the deterministic projection tool, as
# (conservative, base, optimistic). Long-run diversified equity/bond figures —
# they are assumptions, not predictions.
PROJECTION_RATES: tuple[float, float, float] = (2.0, 5.0, 8.0)

__all__ = [
    "EffectiveSettings",
    "UsageTotals",
    "CONTEXT_PLACEHOLDER",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_RATE_LIMIT_MESSAGES",
    "DEFAULT_RATE_LIMIT_WINDOW_SECONDS",
    "HISTORY_MESSAGES",
    "MAX_CONVERSATIONS",
    "MAX_CUSTOM_INSTRUCTIONS_CHARS",
    "MAX_MESSAGE_CHARS",
    "MAX_SYSTEM_PROMPT_CHARS",
    "MAX_TOOL_ITERATIONS",
    "MAX_TOOL_RESULT_ROWS",
    "PROJECTION_RATES",
    "missing_safety_markers",
    "get_settings_row",
    "resolve_settings",
    "month_start",
    "tokens_used_since",
    "usage_totals",
    "usage_by_day",
]


@dataclass(frozen=True)
class EffectiveSettings:
    """Stored overrides resolved against the shipped defaults."""

    custom_instructions: str | None
    system_prompt: str | None
    rate_limit_messages: int
    rate_limit_window_seconds: int
    monthly_token_budget: int | None

    # Which of the above came from the database rather than the environment.
    overridden: frozenset[str] = frozenset()


@dataclass(frozen=True)
class UsageTotals:
    """Token counts over a period."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    messages: int
    summaries: int = 0


async def get_settings_row(db: AsyncSession, user_id: int) -> AssistantSettings | None:
    """Return the user's settings row, or None when they have never saved any."""
    return await db.scalar(
        select(AssistantSettings).where(AssistantSettings.user_id == user_id)
    )


def resolve_settings(row: AssistantSettings | None) -> EffectiveSettings:
    """Resolve stored overrides against the shipped defaults.

    A null column means "use the default", not "zero". That distinction is what
    lets an emptied field in the UI go back to the shipped value instead of
    freezing whatever was typed once.
    """
    overridden: set[str] = set()

    if row is not None and row.rate_limit_messages is not None:
        rate_messages = row.rate_limit_messages
        overridden.add("rate_limit_messages")
    else:
        rate_messages = DEFAULT_RATE_LIMIT_MESSAGES

    if row is not None and row.rate_limit_window_seconds is not None:
        rate_window = row.rate_limit_window_seconds
        overridden.add("rate_limit_window_seconds")
    else:
        rate_window = DEFAULT_RATE_LIMIT_WINDOW_SECONDS

    budget = row.monthly_token_budget if row is not None else None
    if budget is not None:
        overridden.add("monthly_token_budget")

    instructions = (row.custom_instructions or "").strip() if row is not None else ""
    if instructions:
        overridden.add("custom_instructions")

    prompt = (row.system_prompt or "").strip() if row is not None else ""
    if prompt:
        overridden.add("system_prompt")

    return EffectiveSettings(
        custom_instructions=instructions or None,
        system_prompt=prompt or None,
        rate_limit_messages=rate_messages,
        rate_limit_window_seconds=rate_window,
        monthly_token_budget=budget,
        overridden=frozenset(overridden),
    )


def month_start(today: date) -> datetime:
    """First instant of ``today``'s calendar month, in UTC.

    The budget resets on the calendar month rather than on a rolling 30 days
    because that is what a person checking "what has this cost me" expects to
    see, and it lines up with how providers bill.
    """
    return datetime(today.year, today.month, 1, tzinfo=UTC)


async def tokens_used_since(
    db: AsyncSession, user_id: int, since: datetime
) -> int:
    """Total tokens this user's assistant has spent since ``since``.

    Read from the usage ledger, which outlives the conversations: deleting a
    chat must not hand its tokens back to the monthly budget.
    """
    total = await db.scalar(
        select(func.coalesce(func.sum(AssistantUsage.total_tokens), 0)).where(
            AssistantUsage.user_id == user_id,
            AssistantUsage.created_at >= since,
        )
    )
    summary_total = await db.scalar(select(
        func.coalesce(func.sum(ImportSummaryAttempt.total_tokens), 0)
    ).where(
        ImportSummaryAttempt.user_id == user_id,
        ImportSummaryAttempt.created_at >= since,
    ))
    return int(total or 0) + int(summary_total or 0)


async def has_unknown_summary_usage(db: AsyncSession, user_id: int) -> bool:
    return bool(await db.scalar(select(ImportSummaryAttempt.id).where(
        ImportSummaryAttempt.user_id == user_id,
        ImportSummaryAttempt.total_tokens.is_(None),
    ).limit(1)))


def _answers():
    return func.count(case((AssistantUsage.answered, AssistantUsage.id)))


async def usage_totals(
    db: AsyncSession, user_id: int, since: datetime | None = None
) -> UsageTotals:
    """Aggregate token usage, optionally restricted to turns after ``since``.

    ``messages`` counts answers; the token sums also include failed turns, so
    they agree with the monthly budget.
    """
    stmt = select(
        func.coalesce(func.sum(AssistantUsage.prompt_tokens), 0),
        func.coalesce(func.sum(AssistantUsage.completion_tokens), 0),
        func.coalesce(func.sum(AssistantUsage.total_tokens), 0),
        _answers(),
    ).where(AssistantUsage.user_id == user_id)
    if since is not None:
        stmt = stmt.where(AssistantUsage.created_at >= since)

    row = (await db.execute(stmt)).one()
    summary_stmt = select(
        func.coalesce(func.sum(ImportSummaryAttempt.prompt_tokens), 0),
        func.coalesce(func.sum(ImportSummaryAttempt.completion_tokens), 0),
        func.coalesce(func.sum(ImportSummaryAttempt.total_tokens), 0),
        func.count(case((ImportSummaryAttempt.answered.is_(True), ImportSummaryAttempt.id))),
    ).where(ImportSummaryAttempt.user_id == user_id)
    if since is not None:
        summary_stmt = summary_stmt.where(ImportSummaryAttempt.created_at >= since)
    summary = (await db.execute(summary_stmt)).one()
    return UsageTotals(
        prompt_tokens=int(row[0] or 0) + int(summary[0] or 0),
        completion_tokens=int(row[1] or 0) + int(summary[1] or 0),
        total_tokens=int(row[2] or 0) + int(summary[2] or 0),
        messages=int(row[3] or 0),
        summaries=int(summary[3] or 0),
    )


async def usage_by_day(
    db: AsyncSession, user_id: int, since: datetime
) -> list[dict]:
    """Daily token totals since ``since``, chronological, for the usage chart."""
    day = func.to_char(AssistantUsage.created_at, "YYYY-MM-DD")
    rows = (
        await db.execute(
            select(
                day.label("day"),
                func.coalesce(func.sum(AssistantUsage.total_tokens), 0).label("tokens"),
                _answers().label("messages"),
            )
            .where(
                AssistantUsage.user_id == user_id,
                AssistantUsage.created_at >= since,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()

    days = {
        r.day: {"day": r.day, "tokens": int(r.tokens or 0), "messages": int(r.messages),
                "summaries": 0}
        for r in rows
    }
    summary_day = func.to_char(ImportSummaryAttempt.created_at, "YYYY-MM-DD")
    summaries = (await db.execute(select(
        summary_day.label("day"),
        func.coalesce(func.sum(ImportSummaryAttempt.total_tokens), 0).label("tokens"),
        func.count(case(
            (ImportSummaryAttempt.answered.is_(True), ImportSummaryAttempt.id)
        )).label("summaries"),
    ).where(
        ImportSummaryAttempt.user_id == user_id,
        ImportSummaryAttempt.created_at >= since,
    ).group_by(summary_day))).all()
    for summary in summaries:
        point = days.setdefault(summary.day, {
            "day": summary.day, "tokens": 0, "messages": 0, "summaries": 0,
        })
        point["tokens"] += int(summary.tokens or 0)
        point["summaries"] += int(summary.summaries)
    return [days[day] for day in sorted(days)]
