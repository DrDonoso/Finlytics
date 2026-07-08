"""Tests for apply_rules — the Wave-1 rule matcher (pure, synchronous, no DB).

RuleProtocol is satisfied by the lightweight ``_Rule`` dataclass defined here;
no SQLAlchemy import is required.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import pytest

from finlytics.contracts import ExtractedTransaction
from finlytics.extraction.rules import RuleProtocol, apply_rules


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass
class _Rule:
    """Minimal dataclass implementing RuleProtocol for tests."""

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


# Verify _Rule satisfies the protocol at import time
assert isinstance(_Rule(1, "test", "contains", "x"), RuleProtocol)


def _tx(**kwargs) -> ExtractedTransaction:
    """Return a default ExtractedTransaction, overridable via keyword args."""
    defaults: dict = dict(
        transaction_date=date(2024, 6, 15),
        amount=Decimal("-50.00"),
        currency="EUR",
        description="AMAZON MARKETPLACE",
        category="Shopping",
        category_confidence=0.85,
        account_ref="BBVA",
        tags=[],
        merchant="Amazon",
    )
    defaults.update(kwargs)
    return ExtractedTransaction(**defaults)


def _apply(transactions, rules) -> list[ExtractedTransaction]:
    return apply_rules(transactions, rules)


# ---------------------------------------------------------------------------
# description_mode: contains
# ---------------------------------------------------------------------------


def test_contains_mode_matches():
    rule = _Rule(1, "Amazon rule", "contains", "amazon", set_category="Shopping")
    result = _apply([_tx()], [rule])
    assert result[0].matched_rule_id == 1
    assert result[0].category == "Shopping"


def test_contains_mode_no_match():
    rule = _Rule(1, "Mercadona rule", "contains", "mercadona", set_category="Groceries")
    result = _apply([_tx(description="CARREFOUR MARKET")], [rule])
    assert result[0].matched_rule_id is None
    assert result[0].category == "Shopping"


# ---------------------------------------------------------------------------
# description_mode: starts_with
# ---------------------------------------------------------------------------


def test_starts_with_mode_matches():
    rule = _Rule(1, "Amazon SW", "starts_with", "amazon", set_category="Shopping")
    result = _apply([_tx()], [rule])
    assert result[0].matched_rule_id == 1


def test_starts_with_mode_no_match_middle():
    rule = _Rule(1, "Market", "starts_with", "market", set_category="Groceries")
    result = _apply([_tx(description="CARREFOUR MARKET")], [rule])
    assert result[0].matched_rule_id is None


# ---------------------------------------------------------------------------
# description_mode: exact
# ---------------------------------------------------------------------------


def test_exact_mode_matches():
    rule = _Rule(1, "Exact", "exact", "amazon marketplace", set_category="Shopping")
    result = _apply([_tx()], [rule])
    assert result[0].matched_rule_id == 1


def test_exact_mode_no_match_partial():
    rule = _Rule(1, "Exact short", "exact", "amazon", set_category="Shopping")
    result = _apply([_tx()], [rule])
    assert result[0].matched_rule_id is None


# ---------------------------------------------------------------------------
# description_mode: regex
# ---------------------------------------------------------------------------


def test_regex_mode_matches():
    rule = _Rule(1, "Regex", "regex", r"amaz\w+", set_category="Shopping")
    result = _apply([_tx()], [rule])
    assert result[0].matched_rule_id == 1


def test_regex_mode_no_match():
    rule = _Rule(1, "Regex miss", "regex", r"^nomina", set_category="Income")
    result = _apply([_tx()], [rule])
    assert result[0].matched_rule_id is None


def test_malformed_regex_does_not_crash(caplog):
    """A rule with an invalid regex is skipped (no exception), and a warning is logged."""
    bad_rule = _Rule(1, "Bad regex", "regex", r"[unclosed", set_category="Other")
    good_rule = _Rule(2, "Good", "contains", "amazon", set_category="Shopping")

    with caplog.at_level(logging.WARNING, logger="finlytics.extraction.rules"):
        result = _apply([_tx()], [bad_rule, good_rule])

    # Bad rule skipped → good rule matches
    assert result[0].matched_rule_id == 2
    # Warning was emitted
    assert any("invalid regex" in msg.lower() for msg in caplog.messages)


def test_malformed_regex_alone_skips_transaction(caplog):
    """With only a malformed regex rule, the transaction passes through unmatched."""
    bad_rule = _Rule(1, "Bad regex", "regex", r"(unclosed", set_category="Other")

    with caplog.at_level(logging.WARNING, logger="finlytics.extraction.rules"):
        result = _apply([_tx()], [bad_rule])

    assert result[0].matched_rule_id is None
    assert result[0].category == "Shopping"  # AI value preserved


# ---------------------------------------------------------------------------
# Case-insensitivity (all modes)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,value",
    [
        ("contains", "AMAZON"),
        ("contains", "amazon"),
        ("contains", "AmAzOn"),
        ("starts_with", "AMAZON"),
        ("starts_with", "amazon"),
        ("exact", "AMAZON MARKETPLACE"),
        ("exact", "amazon marketplace"),
        ("regex", "AMAZ"),
        ("regex", "amaz"),
    ],
)
def test_case_insensitive(mode, value):
    rule = _Rule(1, "Case test", mode, value, set_category="Shopping")
    result = _apply([_tx(description="Amazon Marketplace")], [rule])
    assert result[0].matched_rule_id == 1, f"Expected match for mode={mode!r}, value={value!r}"


# ---------------------------------------------------------------------------
# amount_sign filter
# ---------------------------------------------------------------------------


def test_amount_sign_negative_matches_expense():
    rule = _Rule(1, "Expense", "contains", "amazon", amount_sign="negative", set_category="Shopping")
    result = _apply([_tx(amount=Decimal("-50.00"))], [rule])
    assert result[0].matched_rule_id == 1


def test_amount_sign_negative_skips_income():
    rule = _Rule(1, "Expense only", "contains", "amazon", amount_sign="negative", set_category="Shopping")
    result = _apply([_tx(amount=Decimal("50.00"))], [rule])
    assert result[0].matched_rule_id is None


def test_amount_sign_positive_matches_income():
    rule = _Rule(1, "Income", "contains", "nomina", amount_sign="positive", set_category="Income")
    result = _apply([_tx(description="NOMINA EMPRESA", amount=Decimal("3200.00"))], [rule])
    assert result[0].matched_rule_id == 1


def test_amount_sign_positive_skips_expense():
    rule = _Rule(1, "Income only", "contains", "amazon", amount_sign="positive", set_category="Income")
    result = _apply([_tx(amount=Decimal("-50.00"))], [rule])
    assert result[0].matched_rule_id is None


def test_amount_sign_none_matches_any():
    rule = _Rule(1, "Any sign", "contains", "amazon", amount_sign=None, set_category="Shopping")
    result_neg = _apply([_tx(amount=Decimal("-50.00"))], [rule])
    result_pos = _apply([_tx(amount=Decimal("50.00"))], [rule])
    assert result_neg[0].matched_rule_id == 1
    assert result_pos[0].matched_rule_id == 1


# ---------------------------------------------------------------------------
# account_ref filter
# ---------------------------------------------------------------------------


def test_account_ref_filter_matches():
    rule = _Rule(1, "BBVA only", "contains", "amazon", account_ref="BBVA", set_category="Shopping")
    result = _apply([_tx(account_ref="BBVA")], [rule])
    assert result[0].matched_rule_id == 1


def test_account_ref_filter_excludes_other_account():
    rule = _Rule(1, "BBVA only", "contains", "amazon", account_ref="BBVA", set_category="Shopping")
    result = _apply([_tx(account_ref="Indexa Capital")], [rule])
    assert result[0].matched_rule_id is None


def test_account_ref_filter_case_insensitive():
    rule = _Rule(1, "BBVA lower", "contains", "amazon", account_ref="bbva", set_category="Shopping")
    result = _apply([_tx(account_ref="BBVA")], [rule])
    assert result[0].matched_rule_id == 1


# ---------------------------------------------------------------------------
# currency filter
# ---------------------------------------------------------------------------


def test_currency_filter_matches():
    rule = _Rule(1, "EUR only", "contains", "amazon", currency="EUR", set_category="Shopping")
    result = _apply([_tx(currency="EUR")], [rule])
    assert result[0].matched_rule_id == 1


def test_currency_filter_excludes_other_currency():
    rule = _Rule(1, "EUR only", "contains", "amazon", currency="EUR", set_category="Shopping")
    result = _apply([_tx(currency="USD")], [rule])
    assert result[0].matched_rule_id is None


def test_currency_filter_case_insensitive():
    rule = _Rule(1, "eur lower", "contains", "amazon", currency="eur", set_category="Shopping")
    result = _apply([_tx(currency="EUR")], [rule])
    assert result[0].matched_rule_id == 1


# ---------------------------------------------------------------------------
# Priority — first-match wins
# ---------------------------------------------------------------------------


def test_lower_priority_wins():
    """Rule with priority=1 should override rule with priority=10."""
    rule_low_prio = _Rule(1, "Groceries rule", "contains", "amazon", priority=1, set_category="Groceries")
    rule_high_prio = _Rule(2, "Shopping rule", "contains", "amazon", priority=10, set_category="Shopping")

    result = _apply([_tx()], [rule_high_prio, rule_low_prio])  # deliberately unordered input

    assert result[0].matched_rule_id == 1
    assert result[0].category == "Groceries"


def test_priority_tie_broken_by_id():
    """When two rules have the same priority, the lower id wins."""
    rule_a = _Rule(1, "Rule A", "contains", "amazon", priority=50, set_category="Groceries")
    rule_b = _Rule(2, "Rule B", "contains", "amazon", priority=50, set_category="Shopping")

    result = _apply([_tx()], [rule_b, rule_a])  # deliberately unordered

    assert result[0].matched_rule_id == 1
    assert result[0].category == "Groceries"


def test_first_match_wins_subsequent_rule_not_evaluated():
    """Once a rule matches, later rules for the same transaction are ignored."""
    winner = _Rule(1, "Winner", "contains", "amazon", priority=1, set_category="Shopping")
    loser = _Rule(2, "Loser", "contains", "amazon", priority=2, set_category="Entertainment")

    result = _apply([_tx()], [winner, loser])

    assert result[0].matched_rule_id == 1
    assert result[0].category == "Shopping"


# ---------------------------------------------------------------------------
# Disabled rule skipped
# ---------------------------------------------------------------------------


def test_disabled_rule_is_skipped():
    disabled = _Rule(1, "Disabled", "contains", "amazon", enabled=False, set_category="Groceries")
    result = _apply([_tx()], [disabled])
    assert result[0].matched_rule_id is None
    assert result[0].category == "Shopping"  # AI value unchanged


def test_disabled_rule_skipped_enabled_rule_matches():
    disabled = _Rule(1, "Disabled", "contains", "amazon", enabled=False, priority=1, set_category="Groceries")
    enabled = _Rule(2, "Enabled", "contains", "amazon", enabled=True, priority=2, set_category="Shopping")

    result = _apply([_tx()], [disabled, enabled])

    assert result[0].matched_rule_id == 2
    assert result[0].category == "Shopping"


# ---------------------------------------------------------------------------
# Partial rule — unset action fields keep AI values
# ---------------------------------------------------------------------------


def test_partial_rule_category_only_preserves_ai_merchant_and_tags():
    """Rule sets category but NOT merchant or tags → AI values are kept."""
    rule = _Rule(1, "Category only", "contains", "amazon", set_category="Electronics")
    tx = _tx(merchant="Amazon", tags=["prime"], category_confidence=0.7)

    result = _apply([tx], [rule])

    assert result[0].category == "Electronics"
    assert result[0].category_confidence == 1.0
    assert result[0].merchant == "Amazon"   # AI value preserved
    assert result[0].tags == ["prime"]       # AI tags preserved


def test_partial_rule_merchant_only_preserves_category():
    rule = _Rule(1, "Merchant only", "contains", "amazon", set_merchant="Amazon Prime")
    tx = _tx(category="Shopping", category_confidence=0.85)

    result = _apply([tx], [rule])

    assert result[0].merchant == "Amazon Prime"
    assert result[0].category == "Shopping"         # AI value preserved
    assert result[0].category_confidence == 0.85    # NOT overridden to 1.0


# ---------------------------------------------------------------------------
# set_category overrides confidence to 1.0
# ---------------------------------------------------------------------------


def test_set_category_forces_confidence_to_one():
    rule = _Rule(1, "Force cat", "contains", "amazon", set_category="Electronics")
    result = _apply([_tx(category_confidence=0.55)], [rule])
    assert result[0].category == "Electronics"
    assert result[0].category_confidence == 1.0


# ---------------------------------------------------------------------------
# add_tags — merge and dedup
# ---------------------------------------------------------------------------


def test_add_tags_appended_to_empty_list():
    rule = _Rule(1, "Tags", "contains", "amazon", add_tags=["prime", "compras"])
    result = _apply([_tx(tags=[])], [rule])
    assert result[0].tags == ["prime", "compras"]


def test_add_tags_appended_to_existing():
    rule = _Rule(1, "Tags", "contains", "amazon", add_tags=["prime"])
    result = _apply([_tx(tags=["compras"])], [rule])
    assert result[0].tags == ["compras", "prime"]


def test_add_tags_dedup_case_insensitive():
    """Tag already present (any case) should not be duplicated."""
    rule = _Rule(1, "Tags", "contains", "amazon", add_tags=["COMPRAS", "prime"])
    result = _apply([_tx(tags=["compras"])], [rule])
    # "COMPRAS" matches existing "compras" → not added; "prime" is new → added
    assert result[0].tags == ["compras", "prime"]


def test_add_tags_preserves_existing_case():
    """Existing tags keep their original case; new tags keep their supplied case."""
    rule = _Rule(1, "Tags", "contains", "amazon", add_tags=["Prime", "luz"])
    result = _apply([_tx(tags=["Compras"])], [rule])
    assert result[0].tags == ["Compras", "Prime", "luz"]


def test_add_tags_existing_order_preserved():
    existing = ["luz", "agua", "gas"]
    rule = _Rule(1, "Tags", "contains", "amazon", add_tags=["internet", "agua"])
    result = _apply([_tx(tags=existing)], [rule])
    # Order: existing intact, only "internet" appended ("agua" is duplicate)
    assert result[0].tags == ["luz", "agua", "gas", "internet"]


def test_add_tags_empty_list_leaves_tags_unchanged():
    rule = _Rule(1, "No tags", "contains", "amazon", add_tags=[], set_category="Shopping")
    result = _apply([_tx(tags=["prime"])], [rule])
    assert result[0].tags == ["prime"]


# ---------------------------------------------------------------------------
# No-match passthrough
# ---------------------------------------------------------------------------


def test_no_match_transaction_untouched():
    """An unmatched transaction must have all AI values and matched_rule_id=None."""
    rule = _Rule(1, "Miss", "contains", "mercadona", set_category="Groceries")
    tx = _tx(description="AMAZON MARKETPLACE", category="Shopping", category_confidence=0.85)

    result = _apply([tx], [rule])

    t = result[0]
    assert t.matched_rule_id is None
    assert t.matched_rule_name is None
    assert t.category == "Shopping"
    assert t.category_confidence == 0.85
    assert t.merchant == "Amazon"


def test_empty_rules_list_returns_transactions_unchanged():
    tx = _tx()
    result = _apply([tx], [])
    assert result[0].matched_rule_id is None
    assert result[0].category == "Shopping"


def test_empty_transactions_returns_empty():
    rule = _Rule(1, "Any", "contains", "amazon", set_category="Shopping")
    result = _apply([], [rule])
    assert result == []


def test_multiple_transactions_each_matched_independently():
    rule_amazon = _Rule(1, "Amazon", "contains", "amazon", priority=1, set_category="Shopping")
    rule_nomina = _Rule(2, "Nomina", "contains", "nomina", priority=2, set_category="Income")

    tx_amazon = _tx(description="AMAZON MARKETPLACE", category="Other")
    tx_nomina = _tx(description="NOMINA EMPRESA", amount=Decimal("3200.00"), category="Other")
    tx_none = _tx(description="RANDOM LINE", category="Other")

    result = _apply([tx_amazon, tx_nomina, tx_none], [rule_amazon, rule_nomina])

    assert result[0].category == "Shopping"
    assert result[0].matched_rule_id == 1
    assert result[1].category == "Income"
    assert result[1].matched_rule_id == 2
    assert result[2].category == "Other"
    assert result[2].matched_rule_id is None


# ---------------------------------------------------------------------------
# Order preservation
# ---------------------------------------------------------------------------


def test_output_order_matches_input_order():
    rule = _Rule(1, "Rule", "contains", "amazon", set_category="Shopping")
    txs = [
        _tx(description=f"TX {i}", category="Other") for i in range(5)
    ] + [_tx(description="AMAZON MARKETPLACE", category="Other")]

    result = _apply(txs, [rule])

    for i, (inp, out) in enumerate(zip(txs, result)):
        assert out.description == inp.description, f"Order mismatch at index {i}"


# ---------------------------------------------------------------------------
# matched_rule_id / matched_rule_name set correctly
# ---------------------------------------------------------------------------


def test_matched_rule_fields_set():
    rule = _Rule(42, "Hipoteca BBVA", "contains", "amortizacion", set_category="Housing")
    result = _apply([_tx(description="AMORTIZACION PRESTAMO")], [rule])
    assert result[0].matched_rule_id == 42
    assert result[0].matched_rule_name == "Hipoteca BBVA"


# ---------------------------------------------------------------------------
# Detail condition — apply_rules (Wave 2 of rules: detail_mode / detail_value)
# ---------------------------------------------------------------------------


def _tx_with_detail(detail: str | None = None, **kwargs) -> ExtractedTransaction:
    """Helper: ExtractedTransaction with an explicit detail value."""
    return _tx(detail=detail, **kwargs)


def test_detail_contains_matches_when_present():
    rule = _Rule(
        1, "Energy detail", "contains", "adeudo",
        detail_mode="contains", detail_value="octopus",
        set_category="Utilities",
    )
    tx = _tx_with_detail(
        description="ADEUDOASUCARGO",
        detail="GCREOCTOPUSENERGY",
    )
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id == 1
    assert result[0].category == "Utilities"


def test_detail_contains_no_match_when_detail_differs():
    rule = _Rule(
        1, "Energy detail", "contains", "adeudo",
        detail_mode="contains", detail_value="iberdrola",
        set_category="Utilities",
    )
    tx = _tx_with_detail(
        description="ADEUDOASUCARGO",
        detail="GCREOCTOPUSENERGY",
    )
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id is None  # AND failed


def test_detail_contains_no_match_when_detail_is_none():
    rule = _Rule(
        1, "Energy detail", "contains", "adeudo",
        detail_mode="contains", detail_value="octopus",
        set_category="Utilities",
    )
    tx = _tx_with_detail(description="ADEUDOASUCARGO", detail=None)
    result = _apply([tx], [rule])
    # detail is None → treated as "" → "octopus" not in "" → no match
    assert result[0].matched_rule_id is None


def test_detail_exact_match():
    rule = _Rule(
        1, "Exact detail rule", "exact", "gcreoctopusenergy",
        detail_mode="exact", detail_value="gcreoctopusenergy",
        set_category="Utilities",
    )
    tx = _tx_with_detail(
        description="GCREOCTOPUSENERGY",
        detail="GCREOCTOPUSENERGY",
    )
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id == 1


def test_detail_starts_with_match():
    rule = _Rule(
        1, "Starts with rule", "contains", "adeudo",
        detail_mode="starts_with", detail_value="gcre",
        set_category="Utilities",
    )
    tx = _tx_with_detail(
        description="ADEUDOASUCARGO",
        detail="GCREOCTOPUSENERGY",
    )
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id == 1


def test_detail_regex_match():
    rule = _Rule(
        1, "Regex detail", "contains", "adeudo",
        detail_mode="regex", detail_value=r"octopus\w+",
        set_category="Utilities",
    )
    tx = _tx_with_detail(
        description="ADEUDOASUCARGO",
        detail="GCREOCTOPUSENERGY",
    )
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id == 1


def test_detail_regex_no_match():
    rule = _Rule(
        1, "Regex detail", "contains", "adeudo",
        detail_mode="regex", detail_value=r"^IBERDROLA",
        set_category="Utilities",
    )
    tx = _tx_with_detail(
        description="ADEUDOASUCARGO",
        detail="GCREOCTOPUSENERGY",
    )
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id is None


def test_detail_case_insensitive():
    rule = _Rule(
        1, "Case insensitive detail", "contains", "adeudo",
        detail_mode="contains", detail_value="OCTOPUS",
        set_category="Utilities",
    )
    tx = _tx_with_detail(
        description="ADEUDOASUCARGO",
        detail="gcreoctopusenergy",  # lowercase detail
    )
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id == 1


def test_detail_condition_backward_compat_no_detail_fields():
    """Rules with no detail_mode/detail_value work exactly as before."""
    rule = _Rule(
        1, "No detail condition", "contains", "amazon",
        set_category="Shopping",
        # detail_mode and detail_value default to None
    )
    tx = _tx(description="AMAZON MARKETPLACE")
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id == 1
    assert result[0].category == "Shopping"


def test_detail_condition_backward_compat_ignores_tx_detail():
    """Rule without detail condition matches regardless of tx.detail content."""
    rule = _Rule(
        1, "No detail condition", "contains", "amazon",
        set_category="Shopping",
    )
    tx = _tx_with_detail(description="AMAZON MARKETPLACE", detail="some detail")
    result = _apply([tx], [rule])
    assert result[0].matched_rule_id == 1

