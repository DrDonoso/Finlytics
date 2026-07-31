"""Tool-call delta reassembly in ``LLMClient.stream_with_tools``.

Streamed tool calls arrive fragmented: the id and function name land in the
first delta for a given index and the arguments dribble in as JSON string
pieces afterwards.  Getting the reassembly wrong produces arguments that parse
as ``{}`` and a tool that quietly queries the wrong thing, so it is worth
pinning down.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from finlytics.extraction.llm_client import (
    LLMClient,
    LLMError,
    TextDelta,
    ToolCallsRequested,
)


def chunk(*, content=None, tool_calls=None):
    """Build the shape the OpenAI SDK yields for one stream chunk."""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def call_delta(index, *, id=None, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=id, function=function)


def client_yielding(chunks, *, error=None) -> LLMClient:
    async def _stream():
        for c in chunks:
            yield c
        if error is not None:
            raise error

    inner = MagicMock()
    inner.chat.completions.create = AsyncMock(return_value=_stream())
    return LLMClient(api_key="k", base_url="u", model="m", _client=inner)


async def drain(client, **kwargs) -> list:
    return [c async for c in client.stream_with_tools([{"role": "user", "content": "hi"}], **kwargs)]


class TestTextStreaming:
    async def test_content_deltas_are_forwarded(self):
        client = client_yielding([chunk(content="Hello "), chunk(content="world")])
        result = await drain(client)
        assert [c.text for c in result if isinstance(c, TextDelta)] == ["Hello ", "world"]

    async def test_empty_deltas_are_skipped(self):
        client = client_yielding([chunk(content=None), chunk(content=""), chunk(content="x")])
        assert [c.text for c in await drain(client)] == ["x"]

    async def test_chunk_without_choices_is_ignored(self):
        # Some providers emit a bare usage/keepalive frame with no choices.
        client = client_yielding([SimpleNamespace(choices=[]), chunk(content="x")])
        assert len(await drain(client)) == 1


class TestToolCallReassembly:
    async def test_arguments_split_across_chunks_are_joined(self):
        client = client_yielding([
            chunk(tool_calls=[call_delta(0, id="c1", name="get_spending_by_category", arguments="")]),
            chunk(tool_calls=[call_delta(0, arguments='{"from_date":')]),
            chunk(tool_calls=[call_delta(0, arguments=' "2026-01-01"}')]),
        ])
        result = await drain(client)

        requested = result[-1]
        assert isinstance(requested, ToolCallsRequested)
        assert len(requested.calls) == 1
        assert requested.calls[0].name == "get_spending_by_category"
        assert requested.calls[0].arguments == '{"from_date": "2026-01-01"}'

    async def test_parallel_calls_are_kept_apart_by_index(self):
        client = client_yielding([
            chunk(tool_calls=[
                call_delta(0, id="a", name="get_spending_by_month"),
                call_delta(1, id="b", name="get_spending_by_category"),
            ]),
            chunk(tool_calls=[call_delta(1, arguments='{"x":')]),
            chunk(tool_calls=[call_delta(0, arguments='{"y": 1}')]),
            chunk(tool_calls=[call_delta(1, arguments=" 2}")]),
        ])
        calls = (await drain(client))[-1].calls

        assert [c.id for c in calls] == ["a", "b"]
        assert calls[0].arguments == '{"y": 1}'
        assert calls[1].arguments == '{"x": 2}'

    async def test_a_call_with_no_arguments_defaults_to_empty_object(self):
        client = client_yielding([
            chunk(tool_calls=[call_delta(0, id="c1", name="list_reference_data")]),
        ])
        assert (await drain(client))[-1].calls[0].arguments == "{}"

    async def test_a_fragment_without_a_name_yields_nothing(self):
        # Unusable: reporting it as a tool call would send the loop after a
        # tool that does not exist.
        client = client_yielding([chunk(tool_calls=[call_delta(0, arguments="{}")])])
        assert await drain(client) == []

    async def test_text_and_tool_calls_can_coexist(self):
        client = client_yielding([
            chunk(content="Let me check. "),
            chunk(tool_calls=[call_delta(0, id="c1", name="get_cashflow", arguments="{}")]),
        ])
        result = await drain(client)
        assert isinstance(result[0], TextDelta)
        assert isinstance(result[-1], ToolCallsRequested)


class TestRequestShape:
    async def test_tools_are_sent_with_auto_choice(self):
        client = client_yielding([chunk(content="x")])
        schemas = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
        await drain(client, tools=schemas)

        kwargs = client._client.chat.completions.create.await_args.kwargs
        assert kwargs["tools"] == schemas
        assert kwargs["tool_choice"] == "auto"
        assert kwargs["stream"] is True

    async def test_no_tool_keys_when_none_are_offered(self):
        # The final pass runs without tools; sending an empty list is not the
        # same thing to every provider.
        client = client_yielding([chunk(content="x")])
        await drain(client, tools=None)

        kwargs = client._client.chat.completions.create.await_args.kwargs
        assert "tools" not in kwargs
        assert "tool_choice" not in kwargs


class TestErrors:
    async def test_upstream_failure_becomes_llm_error(self):
        client = client_yielding([chunk(content="partial")], error=RuntimeError("socket died"))
        with pytest.raises(LLMError, match="socket died"):
            await drain(client)
