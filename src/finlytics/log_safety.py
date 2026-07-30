"""Log-record hygiene for values a user can influence.

An account name, an uploaded filename or a rule's own name all end up in log
lines. A value carrying a newline forges entries: an account named

    Groceries
    2026-07-30 12:00:00 ERROR finlytics.auth Authentication bypassed for admin

reads, in the log file and in anything that ingests it, as two genuine records —
the second one fabricated. Flattening the value at the point where it enters the
log line is what prevents that.

``%r`` formatting escapes newlines as a side effect of ``repr``, which is why
several of these sites were already safe in practice. That is a formatting
choice, not a security control: one edit from ``%r`` to ``%s`` silently removes
it. ``one_line`` makes the guarantee explicit and independent of the format spec.
"""

from __future__ import annotations


def one_line(value: object) -> str:
    """Return *value* as a single-line string, safe to interpolate into a log.

    Breaks are escaped rather than dropped — the goal is to keep one event on
    one line, not to lose what the value actually held.
    """
    # Written as an explicit chain of literals rather than a loop over a tuple
    # of separators: this is the shape both a reader and a static analyser can
    # verify locally. `\r\n` goes first so a CRLF pair collapses to one marker.
    return (
        str(value)
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
