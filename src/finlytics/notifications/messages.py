"""Notification message renderer.

Converts a Notification ORM object (title_key + title_args) into a plain-text
string for delivery via Telegram. Rendered in Spanish (owner locale).

Rules:
- NEVER interpolate secrets (bot_token, chat_id, or any credential).
- title_args values come from the detector, not from user input.
- Unknown keys use a safe generic fallback so future notifications still send.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from finlytics.db.models import Notification


def render_notification_text(notification: "Notification") -> str:
    """Return a human-readable Spanish string for Telegram delivery.

    Args:
        notification: A committed Notification ORM row (has title_key, title_args).

    Returns:
        A safe, non-empty string. Never raises.
    """
    key: str = notification.title_key or ""
    args: dict = notification.title_args or {}

    if key == "notif.statement_missing":
        account = args.get("account", "—")
        month = args.get("month", "—")
        return f"⚠️ Falta subir el extracto de {account} — {month}"

    if key == "notif.espp_overdue":
        period = args.get("period", "—")
        return f"⚠️ Subida ESPP pendiente — {period}"

    # Generic fallback — readable even for future notification types
    return f"📌 Finlytics: {key or 'nueva notificación'}"
