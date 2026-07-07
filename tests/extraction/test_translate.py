"""Tests for translate_category_name (LLM fully mocked — no live API calls)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from finlytics.extraction.llm_client import LLMClient, LLMError
from finlytics.extraction.translate import _TranslationResult, translate_category_name


def _make_client(name_en: str, name_es: str) -> LLMClient:
    """Return an LLMClient whose .parse() yields a canned _TranslationResult."""
    mock_inner = MagicMock()
    client = LLMClient(
        api_key="test-key",
        base_url="http://localhost",
        model="test-model",
        _client=mock_inner,
    )
    client.parse = AsyncMock(
        return_value=_TranslationResult(name_en=name_en, name_es=name_es)
    )
    return client


# ---------------------------------------------------------------------------
# (a) English input → both labels returned
# ---------------------------------------------------------------------------


async def test_english_input_returns_both_labels():
    client = _make_client(name_en="Pet Care", name_es="Cuidado de Mascotas")
    with (
        patch("finlytics.extraction.translate.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.translate.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await translate_category_name("Pet Care")

    assert result is not None
    assert result["name_en"] == "Pet Care"
    assert result["name_es"] == "Cuidado de Mascotas"


async def test_english_input_with_leading_emoji_returns_both_labels():
    client = _make_client(name_en="Health", name_es="Salud")
    with (
        patch("finlytics.extraction.translate.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.translate.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await translate_category_name("🏥 Health")

    assert result is not None
    assert result["name_en"] == "Health"
    assert result["name_es"] == "Salud"


# ---------------------------------------------------------------------------
# (b) Spanish input → name_en is English, name_es is Spanish
# ---------------------------------------------------------------------------


async def test_spanish_input_name_en_is_english():
    client = _make_client(name_en="Clothing", name_es="Ropa")
    with (
        patch("finlytics.extraction.translate.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.translate.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await translate_category_name("Ropa")

    assert result is not None
    assert result["name_en"] == "Clothing"
    assert result["name_es"] == "Ropa"


async def test_spanish_input_with_emoji_prefix():
    client = _make_client(name_en="Transport", name_es="Transporte")
    with (
        patch("finlytics.extraction.translate.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.translate.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await translate_category_name("🚌 Transporte")

    assert result is not None
    assert result["name_en"] == "Transport"
    assert result["name_es"] == "Transporte"


# ---------------------------------------------------------------------------
# (c) Unconfigured / exception → None
# ---------------------------------------------------------------------------


async def test_unconfigured_llm_returns_none():
    with patch("finlytics.extraction.translate.is_llm_configured", return_value=False):
        result = await translate_category_name("Pet Care")

    assert result is None


async def test_empty_string_returns_none():
    result = await translate_category_name("")
    assert result is None


async def test_whitespace_only_returns_none():
    result = await translate_category_name("   ")
    assert result is None


async def test_llm_error_retries_once_then_returns_none():
    client = LLMClient(
        api_key="test-key",
        base_url="http://localhost",
        model="test-model",
        _client=MagicMock(),
    )
    client.parse = AsyncMock(side_effect=LLMError("network timeout"))

    with (
        patch("finlytics.extraction.translate.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.translate.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await translate_category_name("Groceries")

    assert result is None
    assert client.parse.call_count == 2  # retried exactly once


async def test_unexpected_exception_returns_none_without_retry():
    client = LLMClient(
        api_key="test-key",
        base_url="http://localhost",
        model="test-model",
        _client=MagicMock(),
    )
    client.parse = AsyncMock(side_effect=RuntimeError("unexpected crash"))

    with (
        patch("finlytics.extraction.translate.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.translate.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await translate_category_name("Groceries")

    assert result is None
    assert client.parse.call_count == 1  # no retry for non-LLMError
