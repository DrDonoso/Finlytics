"""Telegram Bot API client.

Module-level functions so tests can patch them without side effects.

Security:
- bot_token is NEVER logged or included in exception messages.
- URLs containing the token are never passed to log statements.
- Only safe error descriptions are surfaced in TelegramError.
- The token is user-supplied yet Telegram requires it inside the URL *path*, so
  it is rebuilt from a fixed alphabet before interpolation — see `_bot_endpoint`.
"""

from __future__ import annotations

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"

# Every character a Telegram bot token may contain: `<bot_id>:<url-safe secret>`.
# Note what is *absent*: `/ ? # % @ \ .` and whitespace — i.e. everything that
# could end the path segment, start a query/fragment, traverse upwards or inject
# a new authority into the URL the token is interpolated into.
_TOKEN_ALPHABET = "-0123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz"
_MAX_TOKEN_LEN = 256


class TelegramError(Exception):
    """Raised on Telegram API failures. Message NEVER contains the bot_token."""


def _bot_endpoint(bot_token: str, method: str) -> str:
    """Build the API URL for *method*, guaranteeing the token cannot alter it.

    ``bot_token`` is attacker-controllable — it arrives in the body of
    ``POST /api/notifications/channels`` — and lands in the URL path, so a token
    containing ``/``, ``?``, ``#``, ``@`` or ``..`` could redirect the request to
    another endpoint or host (server-side request forgery).

    Instead of trusting the input, each character is looked up in
    ``_TOKEN_ALPHABET`` and the *constant's* character is what gets appended, so
    the returned URL provably contains nothing outside that alphabet — a
    property both a reader and static analysis can verify locally. A character
    outside it makes the token invalid and no request is made.
    """
    if not bot_token or len(bot_token) > _MAX_TOKEN_LEN:
        raise TelegramError("Invalid Telegram bot token format.")
    try:
        safe_token = "".join(
            _TOKEN_ALPHABET[_TOKEN_ALPHABET.index(char)] for char in bot_token
        )
    except ValueError:
        # .index() found a character outside the alphabet. `from None` keeps the
        # original exception (and any token fragment) out of the traceback.
        raise TelegramError("Invalid Telegram bot token format.") from None
    return f"{TELEGRAM_API_BASE}/bot{safe_token}/{method}"


async def telegram_get_me(bot_token: str) -> dict:
    """Call getMe to validate the bot token.  Returns the bot's info dict.

    Raises TelegramError with a safe message on a malformed token (rejected
    before any request is made), an invalid token or a network error.
    """
    url = _bot_endpoint(bot_token, "getMe")
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

    Raises TelegramError (safe message, no token) on a malformed token, a
    non-2xx response or Telegram ok:false.
    """
    url = _bot_endpoint(bot_token, "sendMessage")
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
