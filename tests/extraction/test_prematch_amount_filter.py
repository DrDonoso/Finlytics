"""Tests for pre_match_rules amount_min / amount_max magnitude filter.

Lines whose abs(amount) falls outside [amount_min, amount_max] must NOT be
pre-matched — they stay in remaining_text for the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from finlytics.extraction.prematch import pre_match_rules
from finlytics.extraction.rules import RuleProtocol


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

# A single statement line with amount -45,30 (abs = 45.30)
_MERCADONA_LINE = (
    "02/05/2026   COMPRA EN MERCADONA C/MAYOR 1 MADRID              -45,30         1.404,70"
)
# A large income line: amount 2850,00 (abs = 2850.00)
_NOMINA_LINE = (
    "15/05/2026   NOMINA EMPRESA TECH SL                          2.850,00         4.083,40"
)


# ---------------------------------------------------------------------------
# amount_min filter
# ---------------------------------------------------------------------------


def test_prematch_amount_min_excludes_small_amount():
    """Line amount abs=45.30 < amount_min=100 → line NOT consumed, stays in remaining."""
    rule = _Rule(1, "High value", "contains", "mercadona",
                 amount_min=Decimal("100"), set_category="Groceries")
    matched, remaining = pre_match_rules(
        _MERCADONA_LINE, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 0
    assert "MERCADONA" in remaining


def test_prematch_amount_min_passes_large_amount():
    """Line amount abs=2850 >= amount_min=1000 → line IS consumed."""
    rule = _Rule(1, "Salario", "contains", "nomina",
                 amount_min=Decimal("1000"), set_category="Income")
    matched, remaining = pre_match_rules(
        _NOMINA_LINE, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 1
    assert matched[0].amount == Decimal("2850.00")
    assert "NOMINA" not in remaining


def test_prematch_amount_min_boundary_equal_passes():
    """Line amount abs=45.30 == amount_min=45.30 → boundary inclusive, line consumed."""
    rule = _Rule(1, "Exact", "contains", "mercadona",
                 amount_min=Decimal("45.30"), set_category="Groceries")
    matched, remaining = pre_match_rules(
        _MERCADONA_LINE, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 1


# ---------------------------------------------------------------------------
# amount_max filter
# ---------------------------------------------------------------------------


def test_prematch_amount_max_excludes_large_amount():
    """Line amount abs=2850 > amount_max=500 → line NOT consumed."""
    rule = _Rule(1, "Nomina too big", "contains", "nomina",
                 amount_max=Decimal("500"), set_category="Income")
    matched, remaining = pre_match_rules(
        _NOMINA_LINE, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 0
    assert "NOMINA" in remaining


def test_prematch_amount_max_passes_small_amount():
    """Line amount abs=45.30 <= amount_max=100 → line IS consumed."""
    rule = _Rule(1, "Small purchase", "contains", "mercadona",
                 amount_max=Decimal("100"), set_category="Groceries")
    matched, remaining = pre_match_rules(
        _MERCADONA_LINE, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 1
    assert matched[0].amount == Decimal("-45.30")


def test_prematch_amount_max_boundary_equal_passes():
    """Line amount abs=45.30 == amount_max=45.30 → boundary inclusive, line consumed."""
    rule = _Rule(1, "Exact max", "contains", "mercadona",
                 amount_max=Decimal("45.30"), set_category="Groceries")
    matched, remaining = pre_match_rules(
        _MERCADONA_LINE, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 1


# ---------------------------------------------------------------------------
# amount_min + amount_max range filter
# ---------------------------------------------------------------------------


def test_prematch_amount_range_inside_passes():
    """abs=45.30 in [10, 100] → line consumed."""
    rule = _Rule(1, "Medium purchase", "contains", "mercadona",
                 amount_min=Decimal("10"), amount_max=Decimal("100"),
                 set_category="Groceries")
    matched, _ = pre_match_rules(
        _MERCADONA_LINE, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 1


def test_prematch_amount_range_outside_not_consumed():
    """abs=2850 outside [10, 100] → Nomina line NOT consumed; Mercadona (45.30) IS consumed."""
    statement = "\n".join([_MERCADONA_LINE, _NOMINA_LINE])
    rule = _Rule(1, "Both", "regex", "mercadona|nomina",
                 amount_min=Decimal("10"), amount_max=Decimal("100"),
                 set_category="Mixed")
    matched, remaining = pre_match_rules(
        statement, [rule], statement_year=2026, account_ref="BBVA"
    )
    # Only Mercadona (abs=45.30) is inside [10, 100]; Nomina (abs=2850) is not.
    assert len(matched) == 1
    assert matched[0].amount == Decimal("-45.30")
    assert "NOMINA" in remaining


# ---------------------------------------------------------------------------
# Migration: ORM model column check (no live DB required)
# ---------------------------------------------------------------------------


def test_rule_orm_model_has_amount_min_max_columns():
    """Rule ORM model declares amount_min and amount_max as nullable Numeric columns."""
    from sqlalchemy import inspect as sa_inspect
    from finlytics.db.models import Rule

    mapper = sa_inspect(Rule)
    cols = {c.key: c for c in mapper.columns}

    assert "amount_min" in cols, "amount_min column missing from Rule model"
    assert "amount_max" in cols, "amount_max column missing from Rule model"
    assert cols["amount_min"].nullable, "amount_min must be nullable"
    assert cols["amount_max"].nullable, "amount_max must be nullable"
