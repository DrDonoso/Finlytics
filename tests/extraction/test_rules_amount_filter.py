"""Tests for apply_rules amount_min / amount_max magnitude filter.

These filters compare abs(tx.amount) against optional lower/upper bounds.
Tests are pure and synchronous — no DB, no mocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from finlytics.contracts import ExtractedTransaction
from finlytics.extraction.rules import RuleProtocol, apply_rules


# ---------------------------------------------------------------------------
# Minimal _Rule stand-in (same pattern as test_rules.py)
# ---------------------------------------------------------------------------


@dataclass
class _Rule:
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


assert isinstance(_Rule(1, "t", "contains", "x"), RuleProtocol)


def _tx(**kwargs) -> ExtractedTransaction:
    defaults = dict(
        transaction_date=date(2026, 5, 1),
        amount=Decimal("-50.00"),
        currency="EUR",
        description="AMAZON MARKETPLACE",
        category="Shopping",
        category_confidence=0.85,
        account_ref="BBVA",
        tags=[],
    )
    defaults.update(kwargs)
    return ExtractedTransaction(**defaults)


def _apply(transactions, rules):
    return apply_rules(transactions, rules)


# ---------------------------------------------------------------------------
# amount_min — lower bound on abs(amount)
# ---------------------------------------------------------------------------


def test_amount_min_only_matches_when_magnitude_above_bound():
    """abs(-120) = 120 >= 100 → match."""
    rule = _Rule(1, "Big expenses", "contains", "amazon",
                 amount_min=Decimal("100"), set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-120.00"))], [rule])
    assert result[0].matched_rule_id == 1


def test_amount_min_only_no_match_when_magnitude_below_bound():
    """abs(-50) = 50 < 100 → no match."""
    rule = _Rule(1, "Big expenses", "contains", "amazon",
                 amount_min=Decimal("100"), set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-50.00"))], [rule])
    assert result[0].matched_rule_id is None


def test_amount_min_boundary_equal_matches():
    """abs(-100) = 100 >= 100 → match (boundary inclusive)."""
    rule = _Rule(1, "Exact 100", "contains", "amazon",
                 amount_min=Decimal("100"), set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-100.00"))], [rule])
    assert result[0].matched_rule_id == 1


def test_amount_min_uses_abs_for_negative_amount():
    """Magnitude is abs(-200) = 200 >= 150 → match (sign irrelevant)."""
    rule = _Rule(1, "Any big", "contains", "amazon",
                 amount_min=Decimal("150"), set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-200.00"))], [rule])
    assert result[0].matched_rule_id == 1


def test_amount_min_uses_abs_for_positive_amount():
    """Magnitude is abs(200) = 200 >= 150 → match."""
    rule = _Rule(1, "Any big", "contains", "amazon",
                 amount_min=Decimal("150"), set_category="Income")
    result = _apply([_tx(amount=Decimal("200.00"))], [rule])
    assert result[0].matched_rule_id == 1


# ---------------------------------------------------------------------------
# amount_max — upper bound on abs(amount)
# ---------------------------------------------------------------------------


def test_amount_max_only_matches_when_magnitude_below_bound():
    """abs(-50) = 50 <= 100 → match."""
    rule = _Rule(1, "Small expenses", "contains", "amazon",
                 amount_max=Decimal("100"), set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-50.00"))], [rule])
    assert result[0].matched_rule_id == 1


def test_amount_max_only_no_match_when_magnitude_above_bound():
    """abs(-150) = 150 > 100 → no match."""
    rule = _Rule(1, "Small expenses", "contains", "amazon",
                 amount_max=Decimal("100"), set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-150.00"))], [rule])
    assert result[0].matched_rule_id is None


def test_amount_max_boundary_equal_matches():
    """abs(-100) = 100 <= 100 → match (boundary inclusive)."""
    rule = _Rule(1, "Exact 100", "contains", "amazon",
                 amount_max=Decimal("100"), set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-100.00"))], [rule])
    assert result[0].matched_rule_id == 1


# ---------------------------------------------------------------------------
# amount_min + amount_max — range filter
# ---------------------------------------------------------------------------


def test_amount_range_matches_inside():
    """abs(-50) = 50 in [10, 100] → match."""
    rule = _Rule(1, "Medium range", "contains", "amazon",
                 amount_min=Decimal("10"), amount_max=Decimal("100"),
                 set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-50.00"))], [rule])
    assert result[0].matched_rule_id == 1


def test_amount_range_no_match_above_max():
    """abs(-150) = 150 > 100 → no match."""
    rule = _Rule(1, "Medium range", "contains", "amazon",
                 amount_min=Decimal("10"), amount_max=Decimal("100"),
                 set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-150.00"))], [rule])
    assert result[0].matched_rule_id is None


def test_amount_range_no_match_below_min():
    """abs(-5) = 5 < 10 → no match."""
    rule = _Rule(1, "Medium range", "contains", "amazon",
                 amount_min=Decimal("10"), amount_max=Decimal("100"),
                 set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-5.00"))], [rule])
    assert result[0].matched_rule_id is None


# ---------------------------------------------------------------------------
# Composes with amount_sign
# ---------------------------------------------------------------------------


def test_amount_filter_composes_with_amount_sign_both_conditions_must_hold():
    """amount_sign=negative + amount_min=100: a positive tx with high magnitude must fail."""
    rule = _Rule(1, "Big negative", "contains", "amazon",
                 amount_sign="negative", amount_min=Decimal("100"),
                 set_category="Shopping")
    # Positive, high magnitude — fails amount_sign filter
    result = _apply([_tx(amount=Decimal("200.00"))], [rule])
    assert result[0].matched_rule_id is None


def test_amount_filter_composes_with_amount_sign_passes_when_both_hold():
    """amount_sign=negative + amount_min=100: negative tx with high magnitude passes."""
    rule = _Rule(1, "Big negative", "contains", "amazon",
                 amount_sign="negative", amount_min=Decimal("100"),
                 set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-200.00"))], [rule])
    assert result[0].matched_rule_id == 1


# ---------------------------------------------------------------------------
# Rules without the filter are unchanged
# ---------------------------------------------------------------------------


def test_no_amount_filter_rule_matches_any_magnitude():
    """A rule with amount_min=None, amount_max=None behaves as before."""
    rule = _Rule(1, "Any Amazon", "contains", "amazon",
                 set_category="Shopping")
    result_small = _apply([_tx(amount=Decimal("-1.00"))], [rule])
    result_large = _apply([_tx(amount=Decimal("-9999.00"))], [rule])
    assert result_small[0].matched_rule_id == 1
    assert result_large[0].matched_rule_id == 1
