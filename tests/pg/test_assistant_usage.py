"""Assistant token accounting against a real database.

``usage_by_day`` groups with ``to_char``, and the write that bills an unanswered
turn opens a session of its own, so neither runs in the mocked API suite.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from finlytics.api import assistant as assistant_api
from finlytics.assistant import settings as assistant_settings
from finlytics.assistant.service import TurnUsage
from finlytics.db.models import AssistantConversation, AssistantMessage, User

SINCE = datetime(2000, 1, 1, tzinfo=UTC)


async def test_a_turn_that_never_answered_still_counts_against_the_budget(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with sessions() as s, s.begin():
        user = User(username="ana", password_hash="x")
        s.add(user)
        await s.flush()
        conversation = AssistantConversation(user_id=user.id, title="Spending")
        s.add(conversation)
        await s.flush()
        failed = AssistantMessage(conversation_id=conversation.id, role="user", content="q2")
        s.add_all([
            AssistantMessage(conversation_id=conversation.id, role="user", content="q1"),
            AssistantMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="a1",
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
            ),
            failed,
            AssistantMessage(conversation_id=conversation.id, role="user", content="q3"),
        ])
    monkeypatch.setattr(assistant_api, "async_session_factory", sessions)

    await assistant_api._record_unanswered_usage(
        failed.id,
        TurnUsage(prompt_tokens=700, completion_tokens=50, total_tokens=750, reported=True),
    )

    async with sessions() as s:
        budget = await assistant_settings.tokens_used_since(s, user.id, SINCE)
        totals = await assistant_settings.usage_totals(s, user.id)
        by_day = await assistant_settings.usage_by_day(s, user.id, SINCE)

    # The Settings page and the budget read the same rows, so they agree; the
    # message count stays a count of answers.
    assert budget == 870
    assert totals == assistant_settings.UsageTotals(
        prompt_tokens=800, completion_tokens=70, total_tokens=870, messages=1
    )
    assert [(day["tokens"], day["messages"]) for day in by_day] == [(870, 1)]
