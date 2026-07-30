"""Tests for one_line — the log-record flattener.

A value a user controls (account name, uploaded filename, rule name) reaches
log lines. Left alone, a newline inside it forges a second, fabricated record.

Coverage:
  - LF, CRLF and lone CR are all neutralised
  - A CRLF pair collapses to a single marker, not two
  - Content survives — breaks are escaped, not dropped
  - Non-string values are accepted
  - Ordinary values pass through untouched
  - A realistic forged-entry payload cannot produce a second line
"""

from __future__ import annotations

import pytest

from finlytics.log_safety import one_line


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\nb", "a\\nb"),
        ("a\r\nb", "a\\nb"),
        ("a\rb", "a\\rb"),
        ("a\n\nb", "a\\n\\nb"),
    ],
)
def test_breaks_are_escaped(raw: str, expected: str) -> None:
    assert one_line(raw) == expected


def test_crlf_collapses_to_one_marker() -> None:
    """Ordering matters: `\\r\\n` must not become two markers."""
    assert one_line("a\r\nb").count("\\") == 1


def test_ordinary_values_are_untouched() -> None:
    assert one_line("Groceries") == "Groceries"
    assert one_line("ES91 2100 0418 4502 0005 1332") == "ES91 2100 0418 4502 0005 1332"


def test_non_string_values_are_accepted() -> None:
    assert one_line(42) == "42"
    assert one_line(None) == "None"


def test_forged_log_entry_cannot_span_two_lines() -> None:
    """The whole point: one event stays on one line."""
    payload = "Groceries\n2026-07-30 12:00:00 ERROR finlytics.auth Bypassed for admin"

    scrubbed = one_line(payload)

    assert "\n" not in scrubbed
    assert len(scrubbed.splitlines()) == 1
    # The content is preserved so the attempt is still visible in the log.
    assert "Bypassed for admin" in scrubbed
