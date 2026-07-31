"""Thin async wrapper around an OpenAI-compatible endpoint.

Provides a `parse` helper for OpenAI structured outputs
(beta.chat.completions.parse).

Credentials are consumed lazily from finlytics.config.settings so the module is
importable with no live credentials — unit tests inject a mock _client directly.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

if TYPE_CHECKING:
    from finlytics.config import Settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised when the LLM backend returns an unexpected error."""


# ── Streaming event types ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolCallRequest:
    """A tool the model wants executed. ``arguments`` is the raw JSON string."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class TextDelta:
    """A fragment of the assistant's visible answer."""

    text: str


@dataclass(frozen=True)
class ToolCallsRequested:
    """Emitted once, at the end of a stream that ended in tool calls."""

    calls: list[ToolCallRequest]


StreamChunk = TextDelta | ToolCallsRequested


class LLMClient:
    """Async wrapper around AsyncOpenAI pointed at an OpenAI base URL.

    Args:
        api_key:   OpenAI API key (from settings.openai_api_key).
        base_url:  OpenAI base URL (from settings.openai_base_url).
        model:     Model identifier (from settings.openai_model).
        _client:   Optional pre-built AsyncOpenAI — inject a mock for tests.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        _client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        # Real client is only instantiated if no mock is provided.
        # Empty credentials are acceptable here — the constructor must not fail
        # even when env vars are unset (importable without live credentials).
        self._client = _client or AsyncOpenAI(api_key=api_key, base_url=base_url)

    # -------------------------------------------------------------------------
    # Factory
    # -------------------------------------------------------------------------

    @classmethod
    def from_settings(
        cls,
        settings: "Settings",
        *,
        _client: AsyncOpenAI | None = None,
    ) -> "LLMClient":
        """Construct a client from the shared settings singleton."""
        return cls(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            _client=_client,
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_completion_tokens: int = 4096,
    ) -> str:
        """Plain chat completion — returns stripped response text."""
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            log.error("LLMClient.complete error: %s", exc)
            raise LLMError(str(exc)) from exc

    async def parse(
        self,
        system: str,
        user: str,
        response_format: Type[T],
        *,
        temperature: float = 0.0,
        max_completion_tokens: int = 4096,
    ) -> T:
        """Structured-output completion — parses the response into a Pydantic model.

        Uses the OpenAI beta structured-outputs endpoint which guarantees the
        response matches the provided JSON schema. Returns the parsed model
        instance directly.

        Cost guard: temperature defaults to 0.0 — extraction is deterministic
        by design; no creative variation is wanted.
        """
        try:
            resp = await self._client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format=response_format,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
            )
            parsed = resp.choices[0].message.parsed
            if parsed is None:
                raise LLMError(
                    "Structured output parse returned None — "
                    "check model compatibility with structured outputs."
                )
            return parsed
        except LLMError:
            raise
        except Exception as exc:
            log.error("LLMClient.parse error: %s", exc)
            raise LLMError(str(exc)) from exc

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_completion_tokens: int = 2048,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion that may call tools.

        Yields ``TextDelta`` for visible output and, when the model finishes by
        requesting tools, a single ``ToolCallsRequested`` at the end.

        The awkward part is that tool calls arrive fragmented across chunks: the
        id and function name land in the first delta for a given ``index`` and
        the arguments dribble in as JSON string pieces over the following ones.
        They must be reassembled per index before anything can be parsed, which
        is why nothing is emitted until the stream is exhausted.

        Temperature defaults to 0.2 rather than the 0.0 used for extraction:
        conversational answers read as stilted at zero, but this is still low
        enough that the model does not get inventive with figures.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Keyed by the delta's index, which is the only thing tying a fragment
        # to its call — ids are only present on the first fragment.
        pending: dict[int, dict[str, str]] = {}

        try:
            stream = await self._client.chat.completions.create(**kwargs)

            async for chunk in stream:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                content = getattr(delta, "content", None)
                if content:
                    yield TextDelta(content)

                for call in getattr(delta, "tool_calls", None) or []:
                    slot = pending.setdefault(
                        getattr(call, "index", 0) or 0,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if getattr(call, "id", None):
                        slot["id"] = call.id
                    function = getattr(call, "function", None)
                    if function is not None:
                        if getattr(function, "name", None):
                            slot["name"] = function.name
                        if getattr(function, "arguments", None):
                            slot["arguments"] += function.arguments
        except Exception as exc:
            log.error("LLMClient.stream_with_tools error: %s", exc)
            raise LLMError(str(exc)) from exc

        if pending:
            calls = [
                ToolCallRequest(
                    id=slot["id"] or f"call_{index}",
                    name=slot["name"],
                    arguments=slot["arguments"] or "{}",
                )
                for index, slot in sorted(pending.items())
                if slot["name"]
            ]
            # A fragment that never carried a function name is unusable; if that
            # was all we got, the turn produced no tool calls at all and the
            # caller must not be told otherwise.
            if calls:
                yield ToolCallsRequested(calls=calls)


def is_llm_configured(settings: "Settings") -> bool:
    """Return True only when all three OpenAI env vars are non-empty."""
    return bool(
        settings.openai_api_key
        and settings.openai_base_url
        and settings.openai_model
    )
