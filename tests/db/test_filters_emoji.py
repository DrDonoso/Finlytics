"""Split the leading emoji from tag names.

The pattern uses possessive quantifiers to prevent the polynomial ReDoS CodeQL flags.
These tests pin two invariants: the normal split is unchanged, and the degenerate case
(a name made only of emojis) is returned whole instead of being split.
"""

from __future__ import annotations

import time

import pytest

from finlytics.db.queries._filters import _split_leading_emoji

# ── Normal split ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\U0001F4A1 luz", ("\U0001F4A1", "luz")),
        ("\U0001F4A1luz", ("\U0001F4A1", "luz")),
        ("\U0001F4A1\t\tluz", ("\U0001F4A1", "luz")),
        ("\U0001F4A1   luz  ", ("\U0001F4A1", "luz")),
        ("\U0001F4A1\U0001F4A7 suministros", ("\U0001F4A1\U0001F4A7", "suministros")),
        ("\U0001F4A1 luz y gas", ("\U0001F4A1", "luz y gas")),
    ],
)
def test_splits_leading_emoji(raw: str, expected: tuple[str, str]):
    assert _split_leading_emoji(raw) == expected


# ── Names returned unchanged ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw",
    [
        "luz",                                  # no emoji
        "",                                     # empty
        "   ",                                  # only spaces
        "\U0001F4A1",                           # single emoji
        "\U0001F4A1 ",                          # emoji and space
        "\U0001F4A1\U0001F4A7",                 # only emojis, no trailing space
        "\U0001F4A1\U0001F4A7 ",                # only emojis, with trailing space
        "\U0001F4A1 \t\n",                      # emoji and mixed whitespace
    ],
)
def test_returns_name_unchanged(raw: str):
    """Stripping the prefix would leave an empty name, so nothing is touched.

    The two "only emojis" cases changed when the pattern was made possessive:
    "💡💧" previously split into emoji "💡" + name "💧", but "💡💧 " (with a space)
    did not, because splitting relied on backtracking. Now both behave consistently
    and honour the function contract.
    """
    assert _split_leading_emoji(raw) == (None, raw)


# ── No quadratic cost ────────────────────────────────────────────────────────

def test_cost_does_not_grow_quadratically():
    """Time grows linearly, not quadratically, with input length.

    Compares the known worst case (emoji + many spaces with nothing after — the
    shape that forced the engine to try every split) at two sizes differing by 8x.
    With quadratic cost the ratio would be around 64x.

    Note: this test does NOT fail if the pattern is reverted to the permissive one.
    Verified. That pattern was ambiguous on paper, but CPython resolved it in linear
    time, so there was nothing exploitable to measure. This guards against a future
    regression, not proof that a real slowdown was fixed.
    """
    def measure(n: int) -> float:
        input_str = "\U0001F525" + " \t" * n
        start = time.perf_counter()
        for _ in range(200):
            _split_leading_emoji(input_str)
        return time.perf_counter() - start

    measure(100)  # warm-up so import cost is not measured
    short_run = measure(500)
    long_run = measure(4000)

    # Wide margin on purpose: the signal is "not quadratic", not a tight threshold
    # that flickers depending on the CI machine.
    assert long_run < short_run * 24, f"suspicious growth: {short_run=:.4f}s {long_run=:.4f}s"
