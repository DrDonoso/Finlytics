"""Tests for suggest_tag_colors (LLM fully mocked — no live API calls)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from finlytics.extraction.llm_client import LLMClient, LLMError
from finlytics.extraction.tag_colors import _ColorResult, _TagColor, suggest_tag_colors


def _make_client(tag_color_pairs: list[tuple[str, str]]) -> LLMClient:
    """Return an LLMClient whose .parse() yields a canned _ColorResult."""
    client = LLMClient(
        api_key="test-key",
        base_url="http://localhost",
        model="test-model",
        _client=MagicMock(),
    )
    client.parse = AsyncMock(
        return_value=_ColorResult(
            colors=[_TagColor(tag=t, color=c) for t, c in tag_color_pairs]
        )
    )
    return client


# ---------------------------------------------------------------------------
# (a) Valid input → dict with a hex per tag
# ---------------------------------------------------------------------------


async def test_single_tag_returns_hex():
    client = _make_client([("agua", "#3b82f6")])
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua"])

    assert result == {"agua": "#3b82f6"}


async def test_multiple_tags_returns_dict_with_all():
    pairs = [
        ("agua", "#3b82f6"),
        ("luz", "#eab308"),
        ("mascotas", "#a855f7"),
    ]
    client = _make_client(pairs)
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua", "luz", "mascotas"])

    assert result is not None
    assert result["agua"] == "#3b82f6"
    assert result["luz"] == "#eab308"
    assert result["mascotas"] == "#a855f7"
    assert set(result.keys()) == {"agua", "luz", "mascotas"}


async def test_uppercase_hex_is_accepted():
    """Model returns uppercase hex — still a valid #RRGGBB."""
    client = _make_client([("gas", "#F97316")])
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["gas"])

    assert result == {"gas": "#F97316"}


async def test_extra_tags_from_model_are_ignored():
    """Model returns extra tags not in the input — output only contains input tags."""
    pairs = [
        ("agua", "#3b82f6"),
        ("luz", "#eab308"),
        ("extra_unknown", "#ffffff"),
    ]
    client = _make_client(pairs)
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua", "luz"])

    assert result is not None
    assert set(result.keys()) == {"agua", "luz"}


# ---------------------------------------------------------------------------
# (b) Unconfigured / empty / exception → None
# ---------------------------------------------------------------------------


async def test_empty_list_returns_none():
    result = await suggest_tag_colors([])
    assert result is None


async def test_unconfigured_llm_returns_none():
    with patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=False):
        result = await suggest_tag_colors(["agua"])

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
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua"])

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
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua"])

    assert result is None
    assert client.parse.call_count == 1  # no retry for non-LLMError


# ---------------------------------------------------------------------------
# (c) Invalid hex from the model → None
# ---------------------------------------------------------------------------


async def test_invalid_hex_shorthand_returns_none():
    """3-digit CSS shorthand is not a valid #RRGGBB."""
    client = _make_client([("agua", "#f00")])
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua"])

    assert result is None


async def test_invalid_hex_no_hash_returns_none():
    """Bare hex string without '#' prefix is rejected."""
    client = _make_client([("agua", "3b82f6")])
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua"])

    assert result is None


async def test_css_color_name_returns_none():
    """CSS color name instead of hex is rejected."""
    client = _make_client([("luz", "yellow")])
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["luz"])

    assert result is None


async def test_missing_tag_in_response_returns_none():
    """Model omits one of the input tags — result is unusable, return None."""
    # Input has 2 tags but model only returns colour for 1.
    client = _make_client([("agua", "#3b82f6")])
    with (
        patch("finlytics.extraction.tag_colors.is_llm_configured", return_value=True),
        patch(
            "finlytics.extraction.tag_colors.LLMClient.from_settings",
            return_value=client,
        ),
    ):
        result = await suggest_tag_colors(["agua", "luz"])

    assert result is None
