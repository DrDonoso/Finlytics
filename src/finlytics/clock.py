"""Application-local date and time.

``date.today()`` uses the process timezone, and the container runs in UTC: the
Dockerfile does not set ``TZ`` and the base image carries none. Meanwhile
``docker-compose.yml`` exposes ``TIMEZONE`` and ``Settings.timezone`` reads it,
but nothing was applying that setting.

The offset matters to the reminders, which reason in calendar days: with
``Europe/Madrid`` at UTC+2 in summer, between 00:00 and 02:00 the container
still believes it is the previous day, so a statement or ESPP purchase reminder
is evaluated against the wrong date.

Centralised here so the adjustment has a single point of application, and so it
can be substituted in tests without patching ``datetime``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from finlytics.config import settings

__all__ = ["local_timezone", "now", "today"]

# None = not resolved yet. No separate sentinel is needed because the function
# always ends up assigning a valid zone (UTC in the worst case).
_cached_zone: ZoneInfo | timezone | None = None


def local_timezone() -> ZoneInfo | timezone:
    """Zone configured in ``TIMEZONE``, or UTC when it cannot be resolved.

    Degrades to UTC rather than failing: a misspelled zone must not stop the
    application from starting, and the warning is left in the log.
    """
    global _cached_zone
    if _cached_zone is not None:
        return _cached_zone

    try:
        _cached_zone = ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        import logging

        logging.getLogger(__name__).warning(
            "TIMEZONE=%r is not a valid timezone; falling back to UTC.",
            settings.timezone,
        )
        _cached_zone = timezone.utc
    return _cached_zone


def now() -> datetime:
    """Current instant in the configured zone (always tz-aware)."""
    return datetime.now(local_timezone())


def today() -> date:
    """Current calendar day in the configured zone.

    Use this in any logic that talks about "today", "this month" or "N days
    ago": those are concepts of the user's calendar, not of the server's UTC
    clock.
    """
    return now().date()


def reset_cache() -> None:
    """Forget the memoised zone. Intended for tests that change TIMEZONE."""
    global _cached_zone
    _cached_zone = None
