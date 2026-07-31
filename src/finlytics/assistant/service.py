"""The agent loop: LLM → tools → LLM → answer.

Bounded on purpose.  Every iteration is a paid round-trip, and a model that keeps
asking for "one more query" would otherwise bill indefinitely for a single user
message, so ``max_tool_iterations`` is a hard stop rather than a guideline.

The loop yields events instead of returning a string so the API layer can push
them straight down an SSE stream: the user sees "Breaking down by category…"
while the query runs, rather than a spinner with no explanation.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.assistant import context as ctx_module
from finlytics.assistant import prompts, tools as tools_module
from finlytics.extraction.llm_client import (
    LLMClient,
    LLMError,
    TextDelta,
    ToolCallsRequested,
    UsageReported,
)

log = logging.getLogger(__name__)

__all__ = [
    "AssistantEvent",
    "ToolStarted",
    "AnswerDelta",
    "Completed",
    "Failed",
    "AgentLimits",
    "run_turn",
]


# ── Events ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolStarted:
    """A tool is about to run. ``label`` is the UI-facing description."""

    name: str
    label: str


@dataclass(frozen=True)
class AnswerDelta:
    """A fragment of the visible answer."""

    text: str


@dataclass(frozen=True)
class Completed:
    """The turn finished. Carries the full answer and the tool audit trail."""

    answer: str
    tool_calls: list[dict]
    # Summed across every provider call the turn made. Zero when the provider
    # reported nothing — which is not the same as the turn having been free.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    usage_reported: bool = False


@dataclass(frozen=True)
class Failed:
    """The turn could not be completed."""

    message: str


AssistantEvent = ToolStarted | AnswerDelta | Completed | Failed


@dataclass(frozen=True)
class AgentLimits:
    """Cost and size guards, passed in so tests can shrink them."""

    max_tool_iterations: int = 5
    max_tool_result_rows: int = 100
    max_completion_tokens: int = 2048
    projection_rates: tuple[float, float, float] = (2.0, 5.0, 8.0)


@dataclass
class _Turn:
    """Mutable state accumulated while a single turn runs."""

    answer_parts: list[str] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    usage_reported: bool = False


def _truncate_arguments(raw: str, limit: int = 500) -> str:
    """Shorten a tool's raw argument JSON for the audit trail."""
    return raw if len(raw) <= limit else raw[:limit] + "…"


async def run_turn(
    *,
    llm: LLMClient,
    session: AsyncSession,
    user_id: int,
    history: list[dict],
    today: date,
    limits: AgentLimits | None = None,
    custom_instructions: str | None = None,
    background_tasks=None,  # noqa: ANN001 — FastAPI type, kept out of the import graph
) -> AsyncIterator[AssistantEvent]:
    """Run one user turn to completion, yielding events as they happen.

    ``history`` is the already-trimmed list of ``{"role", "content"}`` dicts,
    ending with the new user message. Tool results from previous turns are NOT
    part of it — see ``AssistantMessage`` for why.

    ``custom_instructions`` is the user's own preference text, appended to the
    prompt rather than replacing any of it.
    """
    limits = limits or AgentLimits()

    try:
        financial_context = await ctx_module.build_context(
            session, user_id=user_id, today=today
        )
    except Exception:  # noqa: BLE001
        # Logged, not returned: a database failure's text carries SQL and
        # connection details, and `Failed.message` is rendered in the browser.
        log.exception("Assistant: failed to build ledger context")
        yield Failed("Could not read your financial data. Check the server logs.")
        return

    system_prompt = prompts.build_system_prompt(
        ctx_module.render_context(financial_context),
        custom_instructions=custom_instructions,
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        *history,
    ]

    tool_ctx = tools_module.ToolContext(
        session=session,
        user_id=user_id,
        today=today,
        max_rows=limits.max_tool_result_rows,
        projection_rates=limits.projection_rates,
        background_tasks=background_tasks,
    )
    schemas = tools_module.openai_tool_schemas()

    turn = _Turn()

    for iteration in range(limits.max_tool_iterations + 1):
        # The final iteration runs without tools: offering them again would let
        # the model ask for yet another query it can no longer be given, and it
        # would answer with an apology instead of the data it already has.
        last_pass = iteration == limits.max_tool_iterations
        requested: ToolCallsRequested | None = None

        try:
            async for chunk in llm.stream_with_tools(
                messages,
                tools=None if last_pass else schemas,
                max_completion_tokens=limits.max_completion_tokens,
            ):
                if isinstance(chunk, TextDelta):
                    turn.answer_parts.append(chunk.text)
                    yield AnswerDelta(chunk.text)
                elif isinstance(chunk, ToolCallsRequested):
                    requested = chunk
                elif isinstance(chunk, UsageReported):
                    # Accumulated, not overwritten: a turn with a tool
                    # round-trip bills for every pass, and reporting only the
                    # last one would understate the cost by roughly half.
                    turn.prompt_tokens += chunk.prompt_tokens
                    turn.completion_tokens += chunk.completion_tokens
                    turn.total_tokens += chunk.total_tokens
                    turn.usage_reported = True
        except LLMError as exc:
            # The upstream error text can name the endpoint URL and echo request
            # details, so it stays in the log rather than going down the stream.
            log.error("Assistant: LLM call failed: %s", exc)
            yield Failed(
                "The language model could not be reached. Check the server logs."
            )
            return

        if requested is None:
            break

        # The assistant turn that requested the tools has to go back into the
        # conversation verbatim, or the tool results that follow have nothing to
        # attach to and the provider rejects the next request.
        messages.append(
            {
                "role": "assistant",
                "content": "".join(turn.answer_parts) or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments},
                    }
                    for call in requested.calls
                ],
            }
        )
        # Any text emitted alongside a tool request is preamble ("let me check…"),
        # not the answer. Keeping it would prepend it to the real reply.
        turn.answer_parts.clear()

        for call in requested.calls:
            tool = tools_module.TOOLS.get(call.name)
            yield ToolStarted(name=call.name, label=tool.label if tool else call.name)

            try:
                arguments = json.loads(call.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                result = {"error": f"Could not parse the arguments: {exc}"}
            else:
                result = await tools_module.execute_tool(call.name, arguments, tool_ctx)

            turn.audit.append(
                {
                    "name": call.name,
                    "arguments": _truncate_arguments(call.arguments or "{}"),
                    "ok": "error" not in result,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str, ensure_ascii=False),
                }
            )

    answer = "".join(turn.answer_parts).strip()
    if not answer:
        # Reached when the model spent its whole budget on tool calls and never
        # produced prose. Silence would look like a crash to the user.
        yield Failed("I could not put together an answer for that. Try rephrasing it.")
        return

    yield Completed(
        answer=answer,
        tool_calls=turn.audit,
        prompt_tokens=turn.prompt_tokens,
        completion_tokens=turn.completion_tokens,
        total_tokens=turn.total_tokens,
        usage_reported=turn.usage_reported,
    )
