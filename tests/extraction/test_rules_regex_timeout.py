"""Tests for the ReDoS bound on user-authored rule regexes.

Rule patterns are typed into the UI and executed against every transaction and
every statement line. A shape like ``(a|a)*$`` backtracks exponentially, and
CPython holds the GIL for the whole of a regex match — so without a bound it
freezes the event loop and with it the entire app.

Coverage:
  - A catastrophic pattern returns within the timeout instead of hanging
  - The transaction is left untouched (timeout is treated as "no match")
  - The pattern disables itself: N transactions cost one timeout, not N
  - pre_match_rules is bounded the same way (it shares the compiled pattern)
  - A normal regex rule is unaffected
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from finlytics.contracts import ExtractedTransaction
from finlytics.extraction.prematch import pre_match_rules
from finlytics.extraction.rules import REGEX_TIMEOUT_SECONDS, apply_rules

# Backtracks exponentially in the `regex` engine; `re` never returns on it.
_CATASTROPHIC = r"(a|a)*$"
_EVIL_INPUT = "a" * 40 + "!"


@dataclass
class _Rule:
    """Minimal dataclass implementing RuleProtocol."""

    id: int
    name: str
    description_mode: str
    description_value: str
    priority: int = 100
    enabled: bool = True
    amount_sign: Optional[str] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    account_ref: Optional[str] = None
    currency: Optional[str] = None
    set_category: Optional[str] = None
    set_merchant: Optional[str] = None
    add_tags: list[str] = field(default_factory=list)
    skip_ai: bool = False
    detail_mode: Optional[str] = None
    detail_value: Optional[str] = None


def _tx(description: str) -> ExtractedTransaction:
    return ExtractedTransaction(
        transaction_date=date(2024, 6, 15),
        amount=Decimal("-50.00"),
        currency="EUR",
        description=description,
        category="Shopping",
        category_confidence=0.85,
        account_ref="BBVA",
        tags=[],
        merchant="Amazon",
    )


def test_catastrophic_pattern_returns_and_does_not_match():
    """The rule gives up instead of hanging, and leaves the transaction alone."""
    rule = _Rule(1, "evil", "regex", _CATASTROPHIC, set_category="Hijacked")

    started = time.perf_counter()
    result = apply_rules([_tx(_EVIL_INPUT)], [rule])
    elapsed = time.perf_counter() - started

    assert elapsed < REGEX_TIMEOUT_SECONDS * 3
    assert result[0].matched_rule_id is None
    assert result[0].category == "Shopping"


def test_pattern_disables_itself_after_the_first_timeout():
    """20 transactions must cost one timeout, not twenty."""
    rule = _Rule(1, "evil", "regex", _CATASTROPHIC, set_category="Hijacked")
    transactions = [_tx(_EVIL_INPUT) for _ in range(20)]

    started = time.perf_counter()
    result = apply_rules(transactions, [rule])
    elapsed = time.perf_counter() - started

    # Twenty un-bounded evaluations would take 20x the timeout.
    assert elapsed < REGEX_TIMEOUT_SECONDS * 3
    assert all(tx.matched_rule_id is None for tx in result)


def test_prematch_is_bounded_too():
    """pre_match_rules runs the same patterns once per statement line."""
    rule = _Rule(1, "evil", "regex", _CATASTROPHIC, set_category="Hijacked")
    statement = "\n".join(_EVIL_INPUT for _ in range(20))

    started = time.perf_counter()
    matched, remaining = pre_match_rules(
        statement, [rule], statement_year=2024, account_ref="BBVA"
    )
    elapsed = time.perf_counter() - started

    assert elapsed < REGEX_TIMEOUT_SECONDS * 3
    assert matched == []
    assert remaining.count(_EVIL_INPUT) == 20


def test_normal_regex_rule_still_matches():
    """The bound must not disturb ordinary patterns."""
    rule = _Rule(1, "amazon", "regex", r"^amazon\b", set_category="Shopping")

    result = apply_rules([_tx("AMAZON MARKETPLACE")], [rule])

    assert result[0].matched_rule_id == 1
    assert result[0].category == "Shopping"
