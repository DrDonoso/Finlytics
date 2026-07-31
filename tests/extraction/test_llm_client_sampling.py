"""Sampling parameters sent to the model.

A production 400 is what prompted these:

    Unsupported value: 'temperature' does not support 0.2 with this model.
    Only the default (1) value is supported.

The GPT-5 family and the o-series reject ANY explicit ``temperature``, and
crucially they reject the value that equals their own default too — so
"fall back to 1" does not work, only omitting the key does. Every LLM call
path had one hardcoded, which broke statement extraction, category
translation and tag colouring as well as the assistant.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from finlytics.config import Settings
from finlytics.extraction.llm_client import LLMClient


class _Result(BaseModel):
    value: str


def build_client(**kwargs) -> LLMClient:
    inner = MagicMock()
    inner.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" hi "))]
        )
    )
    inner.beta.chat.completions.parse = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=_Result(value="x")))]
        )
    )

    async def _stream():
        return
        yield  # pragma: no cover — makes this an async generator

    inner.chat.completions.create = AsyncMock(
        side_effect=lambda **kw: (
            _stream() if kw.get("stream")
            else SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=" hi "))]
            )
        )
    )
    return LLMClient(api_key="k", base_url="u", model="m", _client=inner, **kwargs)


class TestTemperatureIsOmittedByDefault:
    async def test_complete_sends_no_temperature(self):
        client = build_client()
        await client.complete("sys", "usr")
        assert "temperature" not in client._client.chat.completions.create.await_args.kwargs

    async def test_parse_sends_no_temperature(self):
        client = build_client()
        await client.parse("sys", "usr", _Result)
        assert "temperature" not in client._client.beta.chat.completions.parse.await_args.kwargs

    async def test_stream_with_tools_sends_no_temperature(self):
        client = build_client()
        async for _ in client.stream_with_tools([{"role": "user", "content": "hi"}]):
            pass
        assert "temperature" not in client._client.chat.completions.create.await_args.kwargs


class TestTemperatureIsSentWhenConfigured:
    """Operators on a model that supports it can still pin determinism."""

    async def test_complete_forwards_the_configured_value(self):
        client = build_client(temperature=0.0)
        await client.complete("sys", "usr")
        assert client._client.chat.completions.create.await_args.kwargs["temperature"] == 0.0

    async def test_parse_forwards_the_configured_value(self):
        client = build_client(temperature=0.3)
        await client.parse("sys", "usr", _Result)
        assert client._client.beta.chat.completions.parse.await_args.kwargs["temperature"] == 0.3

    async def test_stream_forwards_the_configured_value(self):
        client = build_client(temperature=0.7)
        async for _ in client.stream_with_tools([{"role": "user", "content": "hi"}]):
            pass
        assert client._client.chat.completions.create.await_args.kwargs["temperature"] == 0.7

    async def test_zero_is_sent_not_treated_as_unset(self):
        # 0.0 is falsy; a truthiness check here would silently drop it.
        client = build_client(temperature=0)
        assert client._sampling_kwargs() == {"temperature": 0}


class TestSettingsWiring:
    def test_default_settings_leave_temperature_unset(self):
        settings = Settings(auth_secret="x" * 32)
        assert settings.openai_temperature is None
        client = LLMClient.from_settings(settings, _client=MagicMock())
        assert client._sampling_kwargs() == {}

    def test_configured_settings_reach_the_client(self):
        settings = Settings(auth_secret="x" * 32, openai_temperature=0.4)
        client = LLMClient.from_settings(settings, _client=MagicMock())
        assert client._sampling_kwargs() == {"temperature": 0.4}


class TestCallSitesDoNotOverride:
    """The extraction paths must not reintroduce a hardcoded temperature.

    Each of these used to pass ``temperature=0.0`` explicitly, which bypassed
    any client-level policy and produced the production 400 on every import.
    """

    @pytest.mark.parametrize(
        "module_path",
        [
            "src/finlytics/extraction/extractor.py",
            "src/finlytics/extraction/translate.py",
            "src/finlytics/extraction/tag_colors.py",
            "src/finlytics/assistant/service.py",
        ],
    )
    def test_no_hardcoded_temperature(self, module_path):
        from pathlib import Path

        source = Path(module_path).read_text(encoding="utf-8")
        assert "temperature" not in source, (
            f"{module_path} pins a temperature; it belongs in OPENAI_TEMPERATURE "
            "so models that reject the parameter still work."
        )
