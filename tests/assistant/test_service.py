"""Tests for the assistant agent loop.

The LLM is a stub throughout: what is under test is the orchestration — that
tools run, that their results come back in a shape the provider accepts, and
above all that the loop terminates.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.assistant import context as ctx_module
from finlytics.assistant.service import (
    AgentLimits,
    AnswerDelta,
    Completed,
    Failed,
    ToolStarted,
    run_turn,
)
from finlytics.extraction.llm_client import (
    LLMError,
    TextDelta,
    ToolCallRequest,
    ToolCallsRequested,
)


class FakeLLM:
    """Replays a canned script of stream chunks, one list per call."""

    def __init__(self, script: list[list]):
        self.script = script
        self.calls: list[dict] = []

    def stream_with_tools(self, messages, *, tools=None, max_completion_tokens=2048):
        self.calls.append({"messages": list(messages), "tools": tools})
        chunks = self.script.pop(0) if self.script else []

        async def _gen():
            for chunk in chunks:
                if isinstance(chunk, Exception):
                    raise chunk
                yield chunk

        return _gen()


@pytest.fixture
def fake_context():
    """Stub the ledger context so no database is needed."""
    ctx = ctx_module.FinancialContext(
        today=date(2026, 7, 31),
        accounts=[{"id": 1, "name": "BBVA", "currency": "EUR"}],
        categories=[{"id": 7, "name": "Groceries"}],
        tags=["luz"],
        first_transaction=date(2025, 1, 1),
        last_transaction=date(2026, 7, 15),
        has_investments=False,
    )
    with patch.object(ctx_module, "build_context", AsyncMock(return_value=ctx)):
        yield ctx


async def collect(llm, **kwargs) -> list:
    events = []
    async for event in run_turn(
        llm=llm,
        session=MagicMock(),
        user_id=1,
        history=[{"role": "user", "content": "How much did I spend?"}],
        today=date(2026, 7, 31),
        **kwargs,
    ):
        events.append(event)
    return events


class TestSinglePass:
    async def test_plain_answer_streams_and_completes(self, fake_context):
        llm = FakeLLM([[TextDelta("You spent "), TextDelta("320,50 €.")]])
        events = await collect(llm)

        assert [e.text for e in events if isinstance(e, AnswerDelta)] == [
            "You spent ", "320,50 €."
        ]
        completed = events[-1]
        assert isinstance(completed, Completed)
        assert completed.answer == "You spent 320,50 €."
        assert completed.tool_calls == []

    async def test_system_prompt_carries_the_ledger_context(self, fake_context):
        llm = FakeLLM([[TextDelta("ok")]])
        await collect(llm)

        system = llm.calls[0]["messages"][0]
        assert system["role"] == "system"
        assert "id=7 · Groceries" in system["content"]
        assert "2026-07-31" in system["content"]

    async def test_empty_answer_reports_failure(self, fake_context):
        # Silence would look like a crash to the user.
        llm = FakeLLM([[]])
        events = await collect(llm)
        assert isinstance(events[-1], Failed)


class TestToolRoundTrip:
    async def test_tool_runs_and_the_answer_follows(self, fake_context):
        llm = FakeLLM([
            [ToolCallsRequested([
                ToolCallRequest(id="c1", name="get_spending_by_category", arguments="{}")
            ])],
            [TextDelta("Groceries, 320,50 €.")],
        ])

        with patch(
            "finlytics.assistant.tools.queries.get_by_category",
            AsyncMock(return_value=[{"category_id": 7, "category": "Groceries",
                                     "amount": 320.5, "count": 12}]),
        ):
            events = await collect(llm)

        started = [e for e in events if isinstance(e, ToolStarted)]
        assert [e.name for e in started] == ["get_spending_by_category"]
        assert started[0].label  # the UI needs something to show

        completed = events[-1]
        assert isinstance(completed, Completed)
        assert completed.answer == "Groceries, 320,50 €."
        assert completed.tool_calls == [
            {"name": "get_spending_by_category", "arguments": "{}", "ok": True}
        ]

    async def test_tool_result_is_appended_as_a_tool_message(self, fake_context):
        llm = FakeLLM([
            [ToolCallsRequested([
                ToolCallRequest(id="c1", name="get_spending_by_category", arguments="{}")
            ])],
            [TextDelta("done")],
        ])
        with patch(
            "finlytics.assistant.tools.queries.get_by_category",
            AsyncMock(return_value=[]),
        ):
            await collect(llm)

        second_call = llm.calls[1]["messages"]
        # The assistant turn that asked for the tool has to go back verbatim, or
        # the tool result that follows has nothing to attach to.
        assistant_turn = second_call[-2]
        assert assistant_turn["role"] == "assistant"
        assert assistant_turn["tool_calls"][0]["function"]["name"] == "get_spending_by_category"
        tool_turn = second_call[-1]
        assert tool_turn["role"] == "tool"
        assert tool_turn["tool_call_id"] == "c1"

    async def test_preamble_before_a_tool_call_is_not_part_of_the_answer(self, fake_context):
        # "Let me check…" is scaffolding; keeping it would prepend it to the reply.
        llm = FakeLLM([
            [
                TextDelta("Let me check that."),
                ToolCallsRequested([
                    ToolCallRequest(id="c1", name="get_spending_by_category", arguments="{}")
                ]),
            ],
            [TextDelta("You spent 320,50 €.")],
        ])
        with patch(
            "finlytics.assistant.tools.queries.get_by_category",
            AsyncMock(return_value=[]),
        ):
            events = await collect(llm)

        assert events[-1].answer == "You spent 320,50 €."

    async def test_malformed_arguments_come_back_as_a_tool_error(self, fake_context):
        llm = FakeLLM([
            [ToolCallsRequested([
                ToolCallRequest(id="c1", name="get_spending_by_category", arguments="{oops")
            ])],
            [TextDelta("I could not read that.")],
        ])
        events = await collect(llm)

        tool_turn = llm.calls[1]["messages"][-1]
        assert "error" in tool_turn["content"]
        # The model gets a chance to correct itself rather than the turn dying.
        assert isinstance(events[-1], Completed)
        assert events[-1].tool_calls[0]["ok"] is False

    async def test_several_tools_in_one_request_all_run(self, fake_context):
        llm = FakeLLM([
            [ToolCallsRequested([
                ToolCallRequest(id="c1", name="get_spending_by_category", arguments="{}"),
                ToolCallRequest(id="c2", name="get_spending_by_month", arguments="{}"),
            ])],
            [TextDelta("Here you go.")],
        ])
        with patch(
            "finlytics.assistant.tools.queries.get_by_category", AsyncMock(return_value=[])
        ), patch(
            "finlytics.assistant.tools.queries.get_by_month", AsyncMock(return_value=[])
        ):
            events = await collect(llm)

        assert [e.name for e in events if isinstance(e, ToolStarted)] == [
            "get_spending_by_category", "get_spending_by_month"
        ]


class TestBounds:
    async def test_the_loop_cannot_run_forever(self, fake_context):
        # A model that keeps asking for one more query would otherwise bill
        # indefinitely for a single user message.
        endless = [
            [ToolCallsRequested([
                ToolCallRequest(id=f"c{i}", name="get_spending_by_category", arguments="{}")
            ])]
            for i in range(50)
        ]
        llm = FakeLLM(endless)
        with patch(
            "finlytics.assistant.tools.queries.get_by_category", AsyncMock(return_value=[])
        ):
            events = await collect(llm, limits=AgentLimits(max_tool_iterations=3))

        # 3 tool passes + 1 final pass = 4 LLM calls, then it gives up.
        assert len(llm.calls) == 4
        assert isinstance(events[-1], Failed)

    async def test_the_final_pass_is_offered_no_tools(self, fake_context):
        # Otherwise the model asks for a query it can no longer be given and
        # answers with an apology instead of the data it already has.
        llm = FakeLLM([
            [ToolCallsRequested([
                ToolCallRequest(id="c1", name="get_spending_by_category", arguments="{}")
            ])],
            [TextDelta("Final answer.")],
        ])
        with patch(
            "finlytics.assistant.tools.queries.get_by_category", AsyncMock(return_value=[])
        ):
            await collect(llm, limits=AgentLimits(max_tool_iterations=1))

        assert llm.calls[0]["tools"] is not None
        assert llm.calls[1]["tools"] is None

    async def test_row_cap_is_passed_down_to_the_tools(self, fake_context):
        rows = [
            {"category_id": i, "category": f"C{i}", "amount": 1.0, "count": 1}
            for i in range(20)
        ]
        llm = FakeLLM([
            [ToolCallsRequested([
                ToolCallRequest(id="c1", name="get_spending_by_category", arguments="{}")
            ])],
            [TextDelta("done")],
        ])
        with patch(
            "finlytics.assistant.tools.queries.get_by_category", AsyncMock(return_value=rows)
        ):
            await collect(llm, limits=AgentLimits(max_tool_result_rows=2))

        assert '"truncated": true' in llm.calls[1]["messages"][-1]["content"]


class TestFailures:
    async def test_llm_error_becomes_a_failed_event(self, fake_context, caplog):
        llm = FakeLLM([[LLMError("https://api.internal/v1 rejected key sk-abc")]])
        events = await collect(llm)

        # The upstream text can name the endpoint and echo request details, and
        # Failed.message is rendered in the browser — so it is logged instead.
        assert isinstance(events[-1], Failed)
        assert "api.internal" not in events[-1].message
        assert "sk-abc" not in events[-1].message
        assert "api.internal" in caplog.text

    async def test_context_failure_does_not_leak_the_database_error(
        self, caplog
    ):
        llm = FakeLLM([[TextDelta("never reached")]])
        with patch.object(
            ctx_module,
            "build_context",
            AsyncMock(side_effect=RuntimeError("could not connect to host db:5432")),
        ):
            events = await collect(llm)

        assert isinstance(events[0], Failed)
        assert "db:5432" not in events[0].message
        assert "db:5432" in caplog.text

    async def test_context_failure_stops_before_any_llm_call(self):
        llm = FakeLLM([[TextDelta("never reached")]])
        with patch.object(
            ctx_module, "build_context", AsyncMock(side_effect=RuntimeError("no db"))
        ):
            events = await collect(llm)

        assert len(events) == 1
        assert isinstance(events[0], Failed)
        assert llm.calls == []
