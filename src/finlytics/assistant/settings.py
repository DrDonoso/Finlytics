"""Per-user assistant settings, token accounting and limit enforcement.

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
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.assistant.prompts import (
    CONTEXT_PLACEHOLDER,
    DEFAULT_SYSTEM_PROMPT,
    MAX_CUSTOM_INSTRUCTIONS_CHARS,
    MAX_SYSTEM_PROMPT_CHARS,
    missing_safety_markers,
)
from finlytics.config import settings as app_settings
from finlytics.db.models import AssistantMessage, AssistantSettings

log = logging.getLogger(__name__)

__all__ = [
    "EffectiveSettings",
    "UsageTotals",
    "CONTEXT_PLACEHOLDER",
    "DEFAULT_SYSTEM_PROMPT",
    "MAX_CUSTOM_INSTRUCTIONS_CHARS",
    "MAX_SYSTEM_PROMPT_CHARS",
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
    """Stored overrides resolved against the environment defaults."""

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


async def get_settings_row(db: AsyncSession, user_id: int) -> AssistantSettings | None:
    """Return the user's settings row, or None when they have never saved any."""
    return await db.scalar(
        select(AssistantSettings).where(AssistantSettings.user_id == user_id)
    )


def resolve_settings(row: AssistantSettings | None) -> EffectiveSettings:
    """Resolve stored overrides against the environment defaults.

    A null column means "use the environment", not "zero". That distinction is
    what lets an operator keep tuning ``ASSISTANT_*`` in the compose file after
    someone has saved an unrelated field in the UI.
    """
    overridden: set[str] = set()

    if row is not None and row.rate_limit_messages is not None:
        rate_messages = row.rate_limit_messages
        overridden.add("rate_limit_messages")
    else:
        rate_messages = app_settings.assistant_rate_limit_messages

    if row is not None and row.rate_limit_window_seconds is not None:
        rate_window = row.rate_limit_window_seconds
        overridden.add("rate_limit_window_seconds")
    else:
        rate_window = app_settings.assistant_rate_limit_window_seconds

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
    return datetime(today.year, today.month, 1, tzinfo=timezone.utc)


async def tokens_used_since(
    db: AsyncSession, user_id: int, since: datetime
) -> int:
    """Total tokens this user's assistant has spent since ``since``.

    Joins through the conversation because usage is recorded per message and
    only conversations carry the owner.
    """
    from finlytics.db.models import AssistantConversation

    total = await db.scalar(
        select(func.coalesce(func.sum(AssistantMessage.total_tokens), 0))
        .select_from(AssistantMessage)
        .join(
            AssistantConversation,
            AssistantConversation.id == AssistantMessage.conversation_id,
        )
        .where(
            AssistantConversation.user_id == user_id,
            AssistantMessage.created_at >= since,
        )
    )
    return int(total or 0)


async def usage_totals(
    db: AsyncSession, user_id: int, since: datetime | None = None
) -> UsageTotals:
    """Aggregate token usage, optionally restricted to messages after ``since``."""
    from finlytics.db.models import AssistantConversation

    stmt = (
        select(
            func.coalesce(func.sum(AssistantMessage.prompt_tokens), 0),
            func.coalesce(func.sum(AssistantMessage.completion_tokens), 0),
            func.coalesce(func.sum(AssistantMessage.total_tokens), 0),
            func.count(AssistantMessage.id),
        )
        .select_from(AssistantMessage)
        .join(
            AssistantConversation,
            AssistantConversation.id == AssistantMessage.conversation_id,
        )
        .where(
            AssistantConversation.user_id == user_id,
            AssistantMessage.role == "assistant",
        )
    )
    if since is not None:
        stmt = stmt.where(AssistantMessage.created_at >= since)

    row = (await db.execute(stmt)).one()
    return UsageTotals(
        prompt_tokens=int(row[0] or 0),
        completion_tokens=int(row[1] or 0),
        total_tokens=int(row[2] or 0),
        messages=int(row[3] or 0),
    )


async def usage_by_day(
    db: AsyncSession, user_id: int, since: datetime
) -> list[dict]:
    """Daily token totals since ``since``, chronological, for the usage chart."""
    from finlytics.db.models import AssistantConversation

    day = func.to_char(AssistantMessage.created_at, "YYYY-MM-DD")
    rows = (
        await db.execute(
            select(
                day.label("day"),
                func.coalesce(func.sum(AssistantMessage.total_tokens), 0).label("tokens"),
                func.count(AssistantMessage.id).label("messages"),
            )
            .select_from(AssistantMessage)
            .join(
                AssistantConversation,
                AssistantConversation.id == AssistantMessage.conversation_id,
            )
            .where(
                AssistantConversation.user_id == user_id,
                AssistantMessage.role == "assistant",
                AssistantMessage.created_at >= since,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()

    return [
        {"day": r.day, "tokens": int(r.tokens or 0), "messages": int(r.messages)}
        for r in rows
    ]
