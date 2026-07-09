"""Tests for extract_account_number — IBAN extraction from statement headers.

Test IBANs are fabricated (not real owner data); validity verified against
the IBAN mod-97 algorithm implemented in the function under test.

Fabricated IBANs used:
  ES7921000813610123456789  — valid Spanish IBAN (bank code 2100, all else synthetic)
  ES8200000000000000000000  — valid Spanish IBAN with all-zero BBAN
  GB82WEST12345698765432    — well-known Wikipedia test IBAN
"""

from __future__ import annotations

import pytest

from finlytics.extraction.extractor import _is_valid_iban, extract_account_number
from finlytics.extraction import extract_account_number as exported_extract_account_number

# ---------------------------------------------------------------------------
# Known-good fabricated IBANs (mod-97 == 1 verified)
# ---------------------------------------------------------------------------
_ES_IBAN = "ES7921000813610123456789"           # compact form
_ES_IBAN_SPACED = "ES79 2100 0813 6101 2345 6789"  # same IBAN, spaced
_ES_IBAN_ZEROS = "ES8200000000000000000000"     # valid, all-zero BBAN
_GB_IBAN = "GB82WEST12345698765432"             # UK Wikipedia test IBAN


# ---------------------------------------------------------------------------
# Unit tests for _is_valid_iban
# ---------------------------------------------------------------------------


class TestIsValidIban:
    def test_valid_spanish_iban(self):
        assert _is_valid_iban(_ES_IBAN) is True

    def test_valid_all_zeros_iban(self):
        assert _is_valid_iban(_ES_IBAN_ZEROS) is True

    def test_valid_gb_iban(self):
        assert _is_valid_iban(_GB_IBAN) is True

    def test_wrong_check_digits_fails(self):
        # Flip check digits: ES79 → ES00 — checksum will not be 1
        bad = "ES00" + _ES_IBAN[4:]
        assert _is_valid_iban(bad) is False

    def test_too_short_fails(self):
        # 14 chars — below ISO 13616 minimum of 15
        assert _is_valid_iban("ES79210008136") is False

    def test_too_long_fails(self):
        # 35 chars — above ISO 13616 maximum of 34
        assert _is_valid_iban("ES79" + "A" * 31) is False

    def test_no_country_letters_fails(self):
        # Starts with digits — not a country code
        assert _is_valid_iban("79ES" + "0" * 20) is False

    def test_spaces_in_candidate_fails(self):
        # _is_valid_iban expects compact (no spaces); the space guard rejects early
        assert _is_valid_iban(_ES_IBAN_SPACED) is False


# ---------------------------------------------------------------------------
# extract_account_number — happy paths
# ---------------------------------------------------------------------------


class TestExtractAccountNumber:
    """Tests for extract_account_number using minimal fabricated statement snippets."""

    # ── Compact IBAN in header ──────────────────────────────────────────────

    def test_compact_iban_bbva_style_header(self):
        """BBVA-style glued header line with compact IBAN → extracted."""
        text = (
            "EXTRACTOMENSUALDE CUENTASPERSONALES\n"
            "EXTRACTODEJULIO2026 Fechadeemisi\ufffdn: 01/08/2026\n"
            f"IBAN {_ES_IBAN}\n"
            "Saldo inicial: 1.000,00 EUR\n"
        )
        assert extract_account_number(text) == _ES_IBAN

    def test_compact_iban_with_label(self):
        """'IBAN: <compact>' label format → extracted."""
        text = f"Cuenta:\nIBAN: {_ES_IBAN}\nFecha: 01/07/2026\n"
        assert extract_account_number(text) == _ES_IBAN

    # ── Spaced IBAN in header ───────────────────────────────────────────────

    def test_spaced_iban_extracted_and_compacted(self):
        """Spaced IBAN (ES79 2100 ...) → returned as compact string."""
        text = (
            "Extracto de cuenta\n"
            f"IBAN {_ES_IBAN_SPACED}\n"
            "Período: julio 2026\n"
        )
        assert extract_account_number(text) == _ES_IBAN

    def test_spaced_iban_in_bbva_real_header_format(self):
        """Realistic BBVA December header with spaced IBAN."""
        text = (
            "EXTRACTOMENSUALDE CUENTASPERSONALES\n"
            "EXTRACTODEDICIEMBRE2025 Fechadeemisi\ufffdn: 01/01/2026\n"
            f"IBAN {_ES_IBAN_SPACED}\n"
            "Saldo anterior: 500,00 EUR\n"
        )
        assert extract_account_number(text) == _ES_IBAN

    # ── Header wins over body ───────────────────────────────────────────────

    def test_header_iban_returned_not_body_iban(self):
        """Account IBAN in header; different payee IBAN deep in body → header wins."""
        # Build a statement longer than 30 lines; the account IBAN is on line 3
        # and a *different* valid IBAN (_ES_IBAN_ZEROS) appears on line 40.
        header = (
            "Extracto mensual\n"
            "Julio 2026\n"
            f"IBAN {_ES_IBAN}\n"
        )
        body_padding = ("10/07/2026 Pago -50,00 EUR\n") * 37  # lines 4-40
        body_payee = f"Transferencia a: {_ES_IBAN_ZEROS}\n"
        text = header + body_padding + body_payee
        result = extract_account_number(text)
        assert result == _ES_IBAN

    # ── Non-IBAN → None ─────────────────────────────────────────────────────

    def test_no_iban_in_header_returns_none(self):
        """Header with dates and amounts but no IBAN → None."""
        text = (
            "Extracto mensual julio 2026\n"
            "Fecha de emisión: 01/08/2026\n"
            "Saldo inicial: 1.234,56 EUR\n"
            "01/07/2026 Pago recibo -120,00 EUR\n"
        )
        assert extract_account_number(text) is None

    def test_empty_string_returns_none(self):
        assert extract_account_number("") is None

    def test_whitespace_only_returns_none(self):
        assert extract_account_number("   \n\n  ") is None

    # ── Invalid / short account numbers ────────────────────────────────────

    def test_wrong_checksum_not_extracted(self):
        """IBAN-format string with wrong check digits → not returned (fails mod-97)."""
        bad_iban = "ES00" + _ES_IBAN[4:]  # mangled check digits
        text = f"IBAN {bad_iban}\nFecha: 01/07/2026\n"
        assert extract_account_number(text) is None

    def test_local_short_account_number_returns_none(self):
        """A bare 10-digit local account number (CCC) is not an IBAN → None."""
        text = "Cuenta: 21000001230123456789\nFecha: 01/07/2026\n"
        # 26 digits only — no country prefix, fails structure check
        assert extract_account_number(text) is None

    # ── IBAN appears only beyond the 30-line header boundary ───────────────

    def test_iban_only_in_body_beyond_30_lines_returns_none(self):
        """IBAN exists only on line 35 (beyond header window) → None."""
        padding = "transaction line\n" * 31  # 31 lines of body
        text = padding + f"IBAN {_ES_IBAN}\n"
        assert extract_account_number(text) is None

    # ── Export surface ──────────────────────────────────────────────────────

    def test_exported_from_extraction_package(self):
        """extract_account_number is importable from finlytics.extraction."""
        assert exported_extract_account_number is extract_account_number
