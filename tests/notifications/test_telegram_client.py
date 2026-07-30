"""Unit tests for the Telegram Bot API client URL construction.

The bot token is user-supplied and Telegram requires it inside the URL *path*,
so `_bot_endpoint` is the boundary that keeps a hostile token from redirecting
the request elsewhere (partial SSRF).

Coverage:
  - A well-formed token produces the expected api.telegram.org URL
  - Tokens carrying URL metacharacters (/ ? # @ % \\ . whitespace, newline) are
    rejected before any request leaves the process
  - Empty and over-long tokens are rejected
  - The rejection message never echoes the submitted token
  - telegram_get_me / telegram_send_message reject a hostile token without
    touching the network
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from finlytics.notifications.telegram import (
    _MAX_TOKEN_LEN,
    TelegramError,
    _bot_endpoint,
    telegram_get_me,
    telegram_send_message,
)

# Structurally realistic but obviously fake — no digits-then-colon prefix, to
# keep secret scanners from mistaking it for a real token.
_VALID_TOKEN = "test:placeholder_bot_token-123"


def test_bot_endpoint_builds_expected_url():
    assert (
        _bot_endpoint(_VALID_TOKEN, "getMe")
        == f"https://api.telegram.org/bot{_VALID_TOKEN}/getMe"
    )


@pytest.mark.parametrize(
    "token",
    [
        "abc/../../evil",          # path traversal
        "abc/getMe?x=",            # extra path segment + query
        "abc?x=1",                 # query string
        "abc#frag",                # fragment
        "user@evil.example.com",   # userinfo-style host swap
        "abc%2f..%2fevil",         # percent-encoded traversal
        "abc\\evil",               # backslash
        "abc.evil",                # dot
        "abc evil",                # space
        "abc\nevil",               # newline
    ],
)
def test_bot_endpoint_rejects_url_metacharacters(token):
    with pytest.raises(TelegramError):
        _bot_endpoint(token, "getMe")


@pytest.mark.parametrize("token", ["", "a" * (_MAX_TOKEN_LEN + 1)])
def test_bot_endpoint_rejects_empty_and_oversized(token):
    with pytest.raises(TelegramError):
        _bot_endpoint(token, "getMe")


def test_rejection_message_does_not_leak_the_token():
    sentinel = "sentinel/leak/check"
    with pytest.raises(TelegramError) as exc:
        _bot_endpoint(sentinel, "getMe")
    assert sentinel not in str(exc.value)


async def test_get_me_rejects_hostile_token_without_network():
    with patch("httpx.AsyncClient") as client_cls, pytest.raises(TelegramError):
        await telegram_get_me("abc/../evil")
    client_cls.assert_not_called()


async def test_send_message_rejects_hostile_token_without_network():
    with patch("httpx.AsyncClient") as client_cls, pytest.raises(TelegramError):
        await telegram_send_message("abc?x=1", "123456789", "hi")
    client_cls.assert_not_called()
