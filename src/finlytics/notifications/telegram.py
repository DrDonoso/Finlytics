"""Telegram Bot API client.

Module-level functions so tests can patch them without side effects.

Security:
- bot_token is NEVER logged or included in exception messages.
- URLs containing the token are never passed to log statements.
- Only safe error descriptions are surfaced in TelegramError.
"""

from __future__ import annotations

import httpx


class TelegramError(Exception):
    """Raised on Telegram API failures. Message NEVER contains the bot_token."""


async def telegram_get_me(bot_token: str) -> dict:
    """Call getMe to validate the bot token.  Returns the bot's info dict.

    Raises TelegramError with a safe message on invalid token or network error.
    """
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=True, follow_redirects=False) as client:
            resp = await client.get(url)
    except httpx.RequestError:
        raise TelegramError("Could not reach Telegram API — check your network.")

    if resp.status_code != 200:
        raise TelegramError(
            f"Telegram token validation failed (HTTP {resp.status_code})."
        )
    data = resp.json()
    if not data.get("ok"):
        desc = data.get("description", "unknown error")
        raise TelegramError(f"Telegram token rejected: {desc}")
    return data["result"]


async def telegram_send_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send *text* to *chat_id* via the Telegram Bot API.

    Raises TelegramError (safe message, no token) on non-2xx or Telegram ok:false.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=True, follow_redirects=False) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
    except httpx.RequestError:
        raise TelegramError("Could not reach Telegram API — check your network.")

    if resp.status_code < 200 or resp.status_code >= 300:
        raise TelegramError(f"sendMessage failed (HTTP {resp.status_code}).")

    data = resp.json()
    if not data.get("ok"):
        desc = data.get("description", "unknown error")
        raise TelegramError(f"Telegram error: {desc}")
