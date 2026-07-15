"""Tests for fidelity_csv.py — Fidelity 'View open lots' CSV parser.

All fixtures are SYNTHETIC.  No real financial data from the owner's
actual Fidelity export is used here.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finlytics.investments.fidelity_csv import (
    NormalizedLot,
    ParsedOpenLots,
    _detect_currency,
    _parse_date,
    _parse_decimal,
    parse_open_lots_csv,
)

# ---------------------------------------------------------------------------
# Synthetic fixtures — hand-crafted rows, no real financial values.
# ---------------------------------------------------------------------------

# Standard format: US-style decimals (dot), EUR currency footer.
# Contains:
#   - 2 SP lots with different dates and grant dates
#   - 2 IDENTICAL DO lots (same date/qty/price → ordinals 0 and 1)
#   - 1 unique DO lot
#   - 1 Total aggregation row  → must be skipped
#   - 1 separator row (single comma) → must be skipped
#   - Currency footer
_MAIN_CSV = (
    "Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,"
    "Sale availability date,Transfer availability date,"
    "Grant date,Share source,Holding period\n"
    # SP lot — Jun quarter
    "Jun-30-2024,50.0000,2000.00,40.00,2500.00,500.00,"
    "Sep-30-2024,Sep-30-2024,Apr-01-2024,SP,Long\n"
    # SP lot — Mar quarter (different date/grant, short-term)
    "Mar-31-2025,25.0000,1100.00,44.00,1375.00,275.00,"
    "Jun-30-2025,Jun-30-2025,Jan-01-2025,SP,Short\n"
    # DO lot — duplicate 1/2
    "Dec-15-2024,0.5500,22.00,40.00,27.50,5.50,"
    "Mar-15-2025,Mar-15-2025,-,DO,Long\n"
    # DO lot — duplicate 2/2  (identical key → ordinal 1)
    "Dec-15-2024,0.5500,22.00,40.00,27.50,5.50,"
    "Mar-15-2025,Mar-15-2025,-,DO,Long\n"
    # DO lot — unique (different date → ordinal 0)
    "Jan-02-2025,1.1000,44.00,40.00,55.00,11.00,"
    "Apr-02-2025,Apr-02-2025,-,DO,Short\n"
    # Total row → skipped
    "Total,,3186.00,,,,,,,, \n"
    # Separator row → skipped
    ",\n"
    # Currency footer
    "The values are displayed in EUR\n"
)

# EU-decimal style: comma as decimal separator, quoted fields.
# Used to verify the EU numeric path without needing a semicolon delimiter.
_EU_DECIMAL_CSV = (
    "Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,"
    "Sale availability date,Transfer availability date,"
    "Grant date,Share source,Holding period\n"
    # Values use EU decimal (comma) with optional dot thousands separator
    'Jun-30-2024,"50,0000","2.000,00","40,00","2.500,00","500,00",'
    "Sep-30-2024,Sep-30-2024,Apr-01-2024,SP,Long\n"
    ",\n"
    "The values are displayed in EUR\n"
)

# USD currency footer
_USD_CSV = (
    "Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,"
    "Sale availability date,Transfer availability date,"
    "Grant date,Share source,Holding period\n"
    "Jun-30-2024,50.0000,2000.00,40.00,2500.00,500.00,"
    "Sep-30-2024,Sep-30-2024,Apr-01-2024,SP,Long\n"
    ",\n"
    "The values are displayed in USD\n"
)


def _bytes(s: str) -> bytes:
    return s.encode("utf-8")


# ---------------------------------------------------------------------------
# Unit tests for private helpers
# ---------------------------------------------------------------------------

class TestDetectCurrency:
    def test_detects_eur(self):
        assert _detect_currency("The values are displayed in EUR") == "EUR"

    def test_detects_usd(self):
        assert _detect_currency("The values are displayed in USD") == "USD"

    def test_case_insensitive(self):
        assert _detect_currency("the values are displayed in Eur") == "EUR"

    def test_defaults_to_usd_when_missing(self):
        assert _detect_currency("No footer here") == "USD"


class TestParseDate:
    def test_standard_date(self):
        assert _parse_date("Jun-30-2024") == date(2024, 6, 30)

    def test_zero_padded_day(self):
        assert _parse_date("Apr-01-2024") == date(2024, 4, 1)

    def test_dash_returns_none(self):
        assert _parse_date("-") is None

    def test_empty_returns_none(self):
        assert _parse_date("") is None

    def test_whitespace_stripped(self):
        assert _parse_date("  Jan-15-2025  ") == date(2025, 1, 15)

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Cannot parse date"):
            _parse_date("2024-06-30")  # wrong format


class TestParseDecimal:
    def test_us_decimal_dot(self):
        assert _parse_decimal("2000.00") == Decimal("2000.00")

    def test_us_thousands_comma(self):
        assert _parse_decimal("1,234.56") == Decimal("1234.56")

    def test_eu_decimal_comma_eu_style(self):
        assert _parse_decimal("50,0000", eu_style=True) == Decimal("50.0000")

    def test_eu_thousands_and_decimal(self):
        # "2.000,00" → EU style auto-detected (comma is rightmost)
        assert _parse_decimal("2.000,00") == Decimal("2000.00")

    def test_eu_simple_comma_eu_style(self):
        assert _parse_decimal("40,00", eu_style=True) == Decimal("40.00")

    def test_us_ambiguous_single_comma_defaults_to_thousands(self):
        # "1,234" with eu_style=False → thousands separator
        assert _parse_decimal("1,234") == Decimal("1234")

    def test_eu_ambiguous_single_comma_is_decimal(self):
        # "0,55" with eu_style=True → decimal
        assert _parse_decimal("0,55", eu_style=True) == Decimal("0.55")

    def test_plain_integer(self):
        assert _parse_decimal("100") == Decimal("100")

    def test_strips_currency_symbols(self):
        assert _parse_decimal("€2000.00") == Decimal("2000.00")
        assert _parse_decimal("$2000.00") == Decimal("2000.00")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _parse_decimal("")


# ---------------------------------------------------------------------------
# Integration tests for parse_open_lots_csv
# ---------------------------------------------------------------------------

class TestParseOpenLotsCSV:
    @pytest.fixture(scope="class")
    def result(self) -> ParsedOpenLots:
        return parse_open_lots_csv(_bytes(_MAIN_CSV))

    # --- Structure ---

    def test_returns_parsed_open_lots(self, result):
        assert isinstance(result, ParsedOpenLots)

    def test_row_count(self, result):
        # 5 lots: Total row skipped, separator skipped, footer skipped
        assert len(result.lots) == 5

    def test_ticker_is_msft(self, result):
        assert result.ticker == "MSFT"

    # --- Currency ---

    def test_currency_detection_eur(self, result):
        assert result.source_currency == "EUR"

    def test_each_lot_carries_currency(self, result):
        for lot in result.lots:
            assert lot.source_currency == "EUR"

    # --- SP lots ---

    def test_sp_lot_purchase_date(self, result):
        sp = result.lots[0]
        assert sp.purchase_date == date(2024, 6, 30)

    def test_sp_lot_shares_decimal_precision(self, result):
        sp = result.lots[0]
        assert sp.shares == Decimal("50.0000")

    def test_sp_lot_cost_basis(self, result):
        assert result.lots[0].cost_basis == Decimal("2000.00")

    def test_sp_lot_cost_basis_per_share(self, result):
        assert result.lots[0].cost_basis_per_share == Decimal("40.00")

    def test_sp_lot_grant_date_parsed(self, result):
        assert result.lots[0].grant_date == date(2024, 4, 1)
        assert result.lots[1].grant_date == date(2025, 1, 1)

    def test_sp_lot_share_source(self, result):
        assert result.lots[0].share_source == "SP"
        assert result.lots[1].share_source == "SP"

    def test_sp_lot_holding_period_long(self, result):
        assert result.lots[0].holding_period == "Long"

    def test_sp_lot_holding_period_short(self, result):
        assert result.lots[1].holding_period == "Short"

    # --- DO lots ---

    def test_do_lot_grant_date_none(self, result):
        for lot in result.lots[2:]:
            assert lot.grant_date is None, f"Expected None for DO lot: {lot}"

    def test_do_lot_share_source(self, result):
        assert result.lots[2].share_source == "DO"
        assert result.lots[3].share_source == "DO"
        assert result.lots[4].share_source == "DO"

    # --- dedup_ordinal ---

    def test_sp_lots_get_ordinal_zero(self, result):
        # Each SP lot has unique (date, shares, cbps, source) → ordinal 0
        assert result.lots[0].dedup_ordinal == 0
        assert result.lots[1].dedup_ordinal == 0

    def test_identical_do_lots_get_distinct_ordinals(self, result):
        # Lots 2 and 3 share (Dec-15-2024, 0.5500, 40.00, DO)
        assert result.lots[2].dedup_ordinal == 0
        assert result.lots[3].dedup_ordinal == 1

    def test_unique_do_lot_gets_ordinal_zero(self, result):
        # Lot 4 has a different date → forms its own group
        assert result.lots[4].dedup_ordinal == 0

    # --- Total row skipped ---

    def test_total_row_not_in_lots(self, result):
        dates = [lot.purchase_date for lot in result.lots]
        # "Total" row has no valid date — it should never appear
        assert all(isinstance(d, date) for d in dates)
        assert len(result.lots) == 5

    # --- Holding period dash → None ---

    def test_holding_period_dash_not_in_fixture(self, result):
        # All rows in fixture have explicit Long/Short → verify no unexpected None
        assert all(lot.holding_period is not None for lot in result.lots)


class TestEuDecimalFormat:
    """Verify EU-style comma-decimal parsing path."""

    @pytest.fixture(scope="class")
    def result(self) -> ParsedOpenLots:
        return parse_open_lots_csv(_bytes(_EU_DECIMAL_CSV))

    def test_row_count(self, result):
        assert len(result.lots) == 1

    def test_currency_eur(self, result):
        assert result.source_currency == "EUR"

    def test_shares_eu_decimal(self, result):
        # "50,0000" with eu_style=True → Decimal("50.0000")
        assert result.lots[0].shares == Decimal("50.0000")

    def test_cost_basis_eu_thousands_and_decimal(self, result):
        # "2.000,00" → auto-detected EU → Decimal("2000.00")
        assert result.lots[0].cost_basis == Decimal("2000.00")

    def test_cost_basis_per_share_eu_simple(self, result):
        # "40,00" with eu_style=True → Decimal("40.00")
        assert result.lots[0].cost_basis_per_share == Decimal("40.00")

    def test_grant_date_parsed(self, result):
        assert result.lots[0].grant_date == date(2024, 4, 1)


class TestUsdCurrencyDetection:
    def test_usd_detected_from_footer(self):
        result = parse_open_lots_csv(_bytes(_USD_CSV))
        assert result.source_currency == "USD"
        assert result.lots[0].source_currency == "USD"


class TestEdgeCases:
    def test_bom_stripped(self):
        # UTF-8 BOM should be handled transparently
        bom_csv = "\ufeff" + _MAIN_CSV
        result = parse_open_lots_csv(bom_csv.encode("utf-8"))
        assert len(result.lots) == 5

    def test_missing_header_raises(self):
        bad = b"col1,col2,col3\nfoo,bar,baz\n"
        with pytest.raises(ValueError, match="Header row"):
            parse_open_lots_csv(bad)

    def test_holding_period_dash_becomes_none(self):
        csv_with_dash_hp = (
            "Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,"
            "Sale availability date,Transfer availability date,"
            "Grant date,Share source,Holding period\n"
            "Jan-15-2025,0.5000,20.00,40.00,25.00,5.00,"
            "Apr-15-2025,Apr-15-2025,-,DO,-\n"
            ",\n"
            "The values are displayed in EUR\n"
        )
        result = parse_open_lots_csv(csv_with_dash_hp.encode("utf-8"))
        assert result.lots[0].holding_period is None
