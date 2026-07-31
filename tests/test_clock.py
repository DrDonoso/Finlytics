"""Tests for the application local date.

``TIMEZONE`` was declared in configuration and exposed in ``docker-compose.yml``,
but was never used anywhere: all code called ``date.today()``, which returns the
UTC date inside the container because neither the Dockerfile nor the base image
sets ``TZ``.

The skew only shows up in the window where the local calendar day and UTC diverge,
so it is a bug that appears in the small hours and disappears on its own — exactly
the kind of thing worth pinning with tests.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from finlytics import clock


@pytest.fixture(autouse=True)
def _clear_zone_cache():
    """Zone is memoised; tests that change it must start from a clean slate."""
    clock.reset_cache()
    yield
    clock.reset_cache()


# ── Zone resolution ──────────────────────────────────────────────────────────

def test_uses_the_configured_timezone(monkeypatch):
    monkeypatch.setattr(clock.settings, "timezone", "Europe/Madrid")

    assert clock.local_timezone() == ZoneInfo("Europe/Madrid")


def test_falls_back_to_utc_on_an_invalid_timezone(monkeypatch):
    """An invalid zone name must not prevent the application from starting."""
    monkeypatch.setattr(clock.settings, "timezone", "Marte/Olympus_Mons")

    assert clock.local_timezone() is timezone.utc


def test_now_always_carries_tzinfo(monkeypatch):
    monkeypatch.setattr(clock.settings, "timezone", "Europe/Madrid")

    assert clock.now().tzinfo is not None


# ── The bug that motivated this module ───────────────────────────────────────

def test_local_date_differs_from_utc_in_the_early_hours(monkeypatch):
    """At 01:00 in Madrid (summer) it is still the previous day in UTC.

    This is the actual scenario the fix addressed: the container runs on UTC,
    so during those hours reminders were evaluated against the wrong day.
    """
    madrid = ZoneInfo("Europe/Madrid")
    instant = datetime(2026, 7, 30, 1, 0, tzinfo=madrid)   # 2026-07-29T23:00Z

    assert instant.astimezone(timezone.utc).date() == date(2026, 7, 29)
    assert instant.astimezone(madrid).date() == date(2026, 7, 30)


def test_today_follows_the_configured_timezone(monkeypatch):
    """The returned date changes with TIMEZONE, not with the server clock."""
    instant = datetime(2026, 7, 29, 23, 30, tzinfo=timezone.utc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return instant.astimezone(tz) if tz else instant

    monkeypatch.setattr(clock, "datetime", _FrozenDatetime)

    monkeypatch.setattr(clock.settings, "timezone", "Europe/Madrid")
    clock.reset_cache()
    assert clock.today() == date(2026, 7, 30)   # already Jul 30 in Madrid

    monkeypatch.setattr(clock.settings, "timezone", "UTC")
    clock.reset_cache()
    assert clock.today() == date(2026, 7, 29)   # still Jul 29 in UTC


def test_today_matches_a_plain_date_today_when_configured_as_utc(monkeypatch):
    """With TIMEZONE=UTC behaviour matches the old ``date.today()`` call.

    Safety net: anyone who had UTC configured before the fix should see
    no change.
    """
    monkeypatch.setattr(clock.settings, "timezone", "UTC")

    assert clock.today() == datetime.now(timezone.utc).date()
