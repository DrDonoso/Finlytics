"""Tests for pre_match_rules — Phase 2 pre-LLM rule matcher.

Covers:
- BBVA and Indexa Capital line extraction (date, amount, description, balance)
- European number / date parsing edge cases
- pre_match_rules: matched tx fields, line removal, remaining_text contents
- Safety net: description matches but line unparseable → warning + line kept
- Rule without set_category → skipped (line goes to LLM)
- All lines matched → remaining_text blank/whitespace
- amount_sign / account_ref / currency filters
- Priority (first-match wins), disabled rules
- set_merchant, add_tags, raw_line, balance_after population
- Regex rule mode
- Generic extractor fallback for unknown account_ref
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import pytest

from finlytics.contracts import ExtractedTransaction
from finlytics.extraction.prematch import (
    _extract_bbva,
    _extract_generic,
    _extract_indexa,
    _parse_european_amount,
    _parse_european_date,
    pre_match_rules,
)
from finlytics.extraction.rules import RuleProtocol


# ---------------------------------------------------------------------------
# Minimal _Rule stand-in (mirrors test_rules.py)
# ---------------------------------------------------------------------------


@dataclass
class _Rule:
    """Minimal dataclass satisfying RuleProtocol — no DB import needed."""

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


# ---------------------------------------------------------------------------
# Statement fixtures (derived from tests/fixtures/statements/)
# ---------------------------------------------------------------------------

BBVA_STATEMENT = """\
BBVA
EXTRACTO DE CUENTA CORRIENTE
Periodo: 01/05/2026 - 31/05/2026

02/05/2026   COMPRA EN MERCADONA C/MAYOR 1 MADRID              -45,30         1.404,70
05/05/2026   RECIBO ENDESA LUZ MAY26                           -78,50         1.326,20
15/05/2026   NOMINA EMPRESA TECH SL                          2.850,00         4.083,40
18/05/2026   DEVOLUCION AMAZON EU SARL                          29,99          4.113,39
20/05/2026   COMPRA EN EXTERIOR AMAZON USA                     -25,00 USD      4.090,24

Saldo final (31/05/2026): 4.090,24"""

INDEXA_STATEMENT = """\
INDEXA CAPITAL
EXTRACTO DE CARTERA - MAYO 2026

05/05/2026   APORTACION PERIODICA AUTOMATICA                  +500,00       12.950,00
12/05/2026   COMISION DE GESTION INDEXA CAPITAL                 -3,25       12.946,75
28/05/2026   TRANSFERENCIA A ES49 0182 6370 8002 0151 3307    -200,00       12.768,00"""

# Only transaction lines — used in the "all matched" test
_BBVA_TX_ONLY = "\n".join([
    "02/05/2026   COMPRA EN MERCADONA C/MAYOR 1 MADRID              -45,30         1.404,70",
    "05/05/2026   RECIBO ENDESA LUZ MAY26                           -78,50         1.326,20",
])


# ---------------------------------------------------------------------------
# _parse_european_amount
# ---------------------------------------------------------------------------


def test_parse_amount_negative():
    assert _parse_european_amount("-45,30") == Decimal("-45.30")


def test_parse_amount_positive_unsigned():
    assert _parse_european_amount("2.850,00") == Decimal("2850.00")


def test_parse_amount_explicit_plus():
    assert _parse_european_amount("+500,00") == Decimal("500.00")


def test_parse_amount_small_no_thousands():
    assert _parse_european_amount("-3,25") == Decimal("-3.25")


def test_parse_amount_multiple_thousands_groups():
    assert _parse_european_amount("1.234.567,89") == Decimal("1234567.89")


def test_parse_amount_period_as_thousands_separator():
    """Period is the European thousands separator — never the decimal point."""
    # "45.30" in European format means 4530 (period = thousands sep, no decimal)
    assert _parse_european_amount("45.30") == Decimal("4530")


def test_parse_amount_small_positive_float():
    assert _parse_european_amount("+8,75") == Decimal("8.75")


def test_parse_amount_zero_decimal():
    assert _parse_european_amount("+0,50") == Decimal("0.50")


# ---------------------------------------------------------------------------
# _parse_european_date
# ---------------------------------------------------------------------------


def test_parse_date_full_year_takes_precedence():
    """When the year is embedded in the string, the statement_year arg is ignored."""
    assert _parse_european_date("02/05/2026", 2024) == date(2026, 5, 2)


def test_parse_date_short_uses_statement_year():
    assert _parse_european_date("15/06", 2026) == date(2026, 6, 15)


def test_parse_date_invalid_string_raises():
    with pytest.raises(ValueError):
        _parse_european_date("notadate", 2026)


def test_parse_date_wrong_segment_count_raises():
    with pytest.raises(ValueError):
        _parse_european_date("2026/05/15/extra", 2026)


# ---------------------------------------------------------------------------
# _extract_bbva — transaction lines
# ---------------------------------------------------------------------------


def test_extract_bbva_expense():
    line = "02/05/2026   COMPRA EN MERCADONA C/MAYOR 1 MADRID              -45,30         1.404,70"
    r = _extract_bbva(line, 2026)
    assert r is not None
    assert r.date == date(2026, 5, 2)
    assert r.amount == Decimal("-45.30")
    assert r.balance_after == Decimal("1404.70")
    assert "MERCADONA" in r.description


def test_extract_bbva_income_no_sign():
    """BBVA income lines have no leading + sign."""
    line = "15/05/2026   NOMINA EMPRESA TECH SL                          2.850,00         4.083,40"
    r = _extract_bbva(line, 2026)
    assert r is not None
    assert r.amount == Decimal("2850.00")
    assert r.description == "NOMINA EMPRESA TECH SL"


def test_extract_bbva_refund_unsigned():
    line = "18/05/2026   DEVOLUCION AMAZON EU SARL                          29,99          4.113,39"
    r = _extract_bbva(line, 2026)
    assert r is not None
    assert r.amount == Decimal("29.99")


def test_extract_bbva_foreign_currency_suffix_ignored():
    """'USD' suffix on BBVA foreign lines is consumed but does not affect amount."""
    line = "20/05/2026   COMPRA EN EXTERIOR AMAZON USA                     -25,00 USD      4.090,24"
    r = _extract_bbva(line, 2026)
    assert r is not None
    assert r.amount == Decimal("-25.00")


def test_extract_bbva_header_returns_none():
    assert _extract_bbva("Fecha        Concepto                      Importe        Saldo", 2026) is None


def test_extract_bbva_blank_line_returns_none():
    assert _extract_bbva("", 2026) is None


def test_extract_bbva_summary_line_returns_none():
    assert _extract_bbva("Saldo final (31/05/2026): 4.090,24", 2026) is None


# ---------------------------------------------------------------------------
# _extract_indexa — transaction lines
# ---------------------------------------------------------------------------


def test_extract_indexa_deposit_with_plus():
    line = "05/05/2026   APORTACION PERIODICA AUTOMATICA                  +500,00       12.950,00"
    r = _extract_indexa(line, 2026)
    assert r is not None
    assert r.date == date(2026, 5, 5)
    assert r.amount == Decimal("500.00")
    assert r.description == "APORTACION PERIODICA AUTOMATICA"


def test_extract_indexa_fee():
    line = "12/05/2026   COMISION DE GESTION INDEXA CAPITAL                 -3,25       12.946,75"
    r = _extract_indexa(line, 2026)
    assert r is not None
    assert r.amount == Decimal("-3.25")


def test_extract_indexa_transfer_with_iban_in_description():
    """Spaces within an IBAN in the description should not confuse the regex."""
    line = "28/05/2026   TRANSFERENCIA A ES49 0182 6370 8002 0151 3307    -200,00       12.768,00"
    r = _extract_indexa(line, 2026)
    assert r is not None
    assert r.amount == Decimal("-200.00")
    assert "TRANSFERENCIA" in r.description


def test_extract_indexa_header_returns_none():
    assert _extract_indexa(
        "Fecha        Concepto                      Importe      Valor Cartera", 2026
    ) is None


# ---------------------------------------------------------------------------
# _extract_generic — fallback for unknown banks
# ---------------------------------------------------------------------------


def test_extract_generic_handles_unknown_bank_format():
    line = "15/06/2026   TRANSFERENCIA BANCO XYZ              -500,00      10.000,00"
    r = _extract_generic(line, 2026)
    assert r is not None
    assert r.amount == Decimal("-500.00")
    assert r.date == date(2026, 6, 15)


def test_extract_generic_returns_none_for_non_tx_line():
    assert _extract_generic("Total movimientos: 5", 2026) is None


# ---------------------------------------------------------------------------
# pre_match_rules — core matching
# ---------------------------------------------------------------------------


def test_matched_line_correct_date_amount_and_rule_fields():
    """A matched BBVA line yields the right date, amount, category, and rule fields."""
    rule = _Rule(1, "Mercadona", "contains", "mercadona", set_category="Groceries")
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")

    assert len(matched) == 1
    tx = matched[0]
    assert tx.transaction_date == date(2026, 5, 2)
    assert tx.amount == Decimal("-45.30")
    assert tx.category == "Groceries"
    assert tx.category_confidence == 1.0
    assert tx.matched_rule_id == 1
    assert tx.matched_rule_name == "Mercadona"
    assert tx.account_ref == "BBVA"
    assert tx.currency == "EUR"


def test_matched_line_removed_from_remaining():
    rule = _Rule(1, "Mercadona", "contains", "mercadona", set_category="Groceries")
    _, remaining = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert "MERCADONA" not in remaining


def test_unmatched_lines_stay_in_remaining():
    rule = _Rule(1, "Mercadona", "contains", "mercadona", set_category="Groceries")
    _, remaining = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert "ENDESA" in remaining
    assert "NOMINA" in remaining


def test_all_transaction_lines_matched_remaining_blank():
    """When every tx line is consumed remaining_text is empty / whitespace."""
    rules = [
        _Rule(1, "Mercadona", "contains", "mercadona", set_category="Groceries"),
        _Rule(2, "Endesa", "contains", "endesa", set_category="Utilities"),
    ]
    matched, remaining = pre_match_rules(
        _BBVA_TX_ONLY, rules, statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 2
    assert not remaining.strip()


# ---------------------------------------------------------------------------
# pre_match_rules — safety net
# ---------------------------------------------------------------------------


def test_safety_net_description_matches_unparseable_line(caplog):
    """Matched description on a non-transaction line → warning + line kept, no tx."""
    summary_line = "Saldo final (31/05/2026): 4.090,24"
    rule = _Rule(1, "Saldo", "contains", "saldo", set_category="Other")

    with caplog.at_level(logging.WARNING, logger="finlytics.extraction.prematch"):
        matched, remaining = pre_match_rules(
            summary_line, [rule], statement_year=2026, account_ref="BBVA"
        )

    assert len(matched) == 0
    assert summary_line in remaining
    assert any("extraction failed" in msg.lower() for msg in caplog.messages)


def test_safety_net_header_line_not_consumed(caplog):
    """Column-header line matching a rule stays in remaining_text."""
    header = "Fecha        Concepto                                          Importe        Saldo"
    rule = _Rule(1, "Fecha", "contains", "fecha", set_category="Other")

    with caplog.at_level(logging.WARNING, logger="finlytics.extraction.prematch"):
        matched, remaining = pre_match_rules(
            header, [rule], statement_year=2026, account_ref="BBVA"
        )

    assert len(matched) == 0
    assert header in remaining


# ---------------------------------------------------------------------------
# pre_match_rules — rule without set_category stays in remaining
# ---------------------------------------------------------------------------


def test_rule_without_category_is_skipped():
    """Rules with set_category=None cannot pre-match; line passes to LLM."""
    rule = _Rule(
        1, "Merchant only", "contains", "mercadona",
        set_category=None, set_merchant="Mercadona",
    )
    matched, remaining = pre_match_rules(
        BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 0
    assert "MERCADONA" in remaining


# ---------------------------------------------------------------------------
# pre_match_rules — amount_sign filter
# ---------------------------------------------------------------------------


def test_amount_sign_negative_matches_expenses_only():
    rule = _Rule(
        1, "Purchases", "contains", "compra",
        amount_sign="negative", set_category="Shopping",
    )
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert len(matched) >= 1
    assert all(tx.amount < 0 for tx in matched)


def test_amount_sign_positive_matches_income_only():
    rule = _Rule(
        1, "Nomina", "contains", "nomina",
        amount_sign="positive", set_category="Income",
    )
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert len(matched) == 1
    assert matched[0].amount == Decimal("2850.00")


def test_amount_sign_positive_excludes_expense():
    """Negative 'compra' lines should not match a positive-only rule."""
    rule = _Rule(
        1, "Positive compra", "contains", "compra",
        amount_sign="positive", set_category="Shopping",
    )
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert len(matched) == 0


# ---------------------------------------------------------------------------
# pre_match_rules — account_ref filter
# ---------------------------------------------------------------------------


def test_account_ref_filter_excludes_wrong_account():
    rule = _Rule(
        1, "BBVA only", "contains", "mercadona",
        account_ref="BBVA", set_category="Groceries",
    )
    matched, remaining = pre_match_rules(
        BBVA_STATEMENT, [rule], statement_year=2026, account_ref="Indexa Capital"
    )
    assert len(matched) == 0
    assert "MERCADONA" in remaining


def test_account_ref_filter_case_insensitive():
    rule = _Rule(
        1, "bbva lowercase", "contains", "mercadona",
        account_ref="bbva", set_category="Groceries",
    )
    matched, _ = pre_match_rules(
        BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 1


# ---------------------------------------------------------------------------
# pre_match_rules — currency filter
# ---------------------------------------------------------------------------


def test_currency_filter_matches_correct_currency():
    rule = _Rule(1, "EUR", "contains", "mercadona", currency="EUR", set_category="Groceries")
    matched, _ = pre_match_rules(
        BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA", currency="EUR"
    )
    assert len(matched) == 1


def test_currency_filter_excludes_wrong_currency():
    rule = _Rule(1, "USD only", "contains", "mercadona", currency="USD", set_category="Groceries")
    matched, _ = pre_match_rules(
        BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA", currency="EUR"
    )
    assert len(matched) == 0


# ---------------------------------------------------------------------------
# pre_match_rules — priority / first-match wins
# ---------------------------------------------------------------------------


def test_priority_first_match_wins():
    rule1 = _Rule(1, "Groceries", "contains", "mercadona", priority=1, set_category="Groceries")
    rule2 = _Rule(2, "Shopping", "contains", "mercadona", priority=2, set_category="Shopping")
    matched, _ = pre_match_rules(
        BBVA_STATEMENT, [rule1, rule2], statement_year=2026, account_ref="BBVA"
    )
    mercadona_txs = [tx for tx in matched if "MERCADONA" in (tx.raw_line or "")]
    assert len(mercadona_txs) == 1
    assert mercadona_txs[0].matched_rule_id == 1
    assert mercadona_txs[0].category == "Groceries"


# ---------------------------------------------------------------------------
# pre_match_rules — disabled rule skipped
# ---------------------------------------------------------------------------


def test_disabled_rule_is_skipped():
    rule = _Rule(1, "Disabled", "contains", "mercadona", enabled=False, set_category="Groceries")
    matched, remaining = pre_match_rules(
        BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA"
    )
    assert len(matched) == 0
    assert "MERCADONA" in remaining


# ---------------------------------------------------------------------------
# pre_match_rules — rule actions applied correctly
# ---------------------------------------------------------------------------


def test_set_merchant_becomes_description():
    rule = _Rule(
        1, "Mercadona", "contains", "mercadona",
        set_category="Groceries", set_merchant="Mercadona",
    )
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert len(matched) == 1
    assert matched[0].description == "Mercadona"
    assert matched[0].merchant == "Mercadona"


def test_set_merchant_none_uses_extracted_description():
    rule = _Rule(1, "Mercadona", "contains", "mercadona", set_category="Groceries")
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert len(matched) == 1
    assert "MERCADONA" in matched[0].description
    assert matched[0].merchant is None


def test_add_tags_applied():
    rule = _Rule(
        1, "Mercadona", "contains", "mercadona",
        set_category="Groceries", add_tags=["alimentacion", "supermercado"],
    )
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert "alimentacion" in matched[0].tags
    assert "supermercado" in matched[0].tags


def test_raw_line_preserved():
    rule = _Rule(1, "Mercadona", "contains", "mercadona", set_category="Groceries")
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert matched[0].raw_line is not None
    assert "MERCADONA" in matched[0].raw_line


def test_balance_after_populated():
    rule = _Rule(1, "Mercadona", "contains", "mercadona", set_category="Groceries")
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert matched[0].balance_after == Decimal("1404.70")


# ---------------------------------------------------------------------------
# pre_match_rules — regex rule mode
# ---------------------------------------------------------------------------


def test_regex_rule_pre_matches():
    rule = _Rule(1, "Regex Mercadona", "regex", r"mercad\w+", set_category="Groceries")
    matched, _ = pre_match_rules(BBVA_STATEMENT, [rule], statement_year=2026, account_ref="BBVA")
    assert len(matched) == 1


# ---------------------------------------------------------------------------
# pre_match_rules — Indexa Capital
# ---------------------------------------------------------------------------


def test_indexa_pre_match_deposit():
    rule = _Rule(1, "Aportacion", "contains", "aportacion", set_category="Savings")
    matched, remaining = pre_match_rules(
        INDEXA_STATEMENT, [rule], statement_year=2026, account_ref="Indexa Capital"
    )
    assert len(matched) == 1
    assert matched[0].amount == Decimal("500.00")
    assert matched[0].transaction_date == date(2026, 5, 5)
    assert "APORTACION" not in remaining


def test_indexa_pre_match_fee_with_negative_filter():
    rule = _Rule(
        1, "Comision", "contains", "comision",
        amount_sign="negative", set_category="Banking",
    )
    matched, _ = pre_match_rules(
        INDEXA_STATEMENT, [rule], statement_year=2026, account_ref="Indexa Capital"
    )
    assert len(matched) == 1
    assert matched[0].amount == Decimal("-3.25")


# ---------------------------------------------------------------------------
# pre_match_rules — generic extractor via unknown account_ref
# ---------------------------------------------------------------------------


def test_generic_extractor_used_for_unknown_account():
    line = "15/06/2026   PAGO BANCO GENERICO                        -100,00       9.900,00"
    rule = _Rule(1, "Pago", "contains", "pago", set_category="Other")
    matched, _ = pre_match_rules(line, [rule], statement_year=2026, account_ref="Otro Banco")
    assert len(matched) == 1
    assert matched[0].amount == Decimal("-100.00")
