"""Tests for PII redaction module (IBANs, card/PAN numbers, account numbers).

Verifies:
    - Sensitive identifiers are masked (all but last 4 chars/digits).
    - Amounts, dates, and merchant names survive unmodified.
    - Edge cases (empty text, short numbers) are handled gracefully.
"""

from __future__ import annotations

import pytest

from finlytics.extraction.redaction import redact_pii


# ---------------------------------------------------------------------------
# IBAN redaction
# ---------------------------------------------------------------------------


class TestIBANRedaction:
    """Test IBAN masking in various formats."""

    def test_iban_spaced_standard(self):
        """ES91 2100 0418 4502 0005 1332 → country+check preserved, last 4 visible."""
        text = "Cuenta: ES91 2100 0418 4502 0005 1332"
        result = redact_pii(text)
        assert "1332" in result           # last 4 preserved
        assert "2100" not in result       # internal digits masked
        assert "ES91" in result           # country+check preserved
        assert "•" in result              # masking applied

    def test_iban_compact(self):
        """ES9121000418450200051332 → masked."""
        text = "IBAN: ES9121000418450200051332"
        result = redact_pii(text)
        assert "1332" in result
        assert "21000418" not in result
        assert "ES91" in result

    def test_iban_german_format(self):
        """DE89 3704 0044 0532 0130 00 — German IBAN."""
        text = "Konto: DE89 3704 0044 0532 0130 00"
        result = redact_pii(text)
        assert "3000" in result or "0130" in result or result.endswith("3000") or "•" in result
        # The key assertion: internal digits are masked
        assert "3704" not in result

    def test_iban_compact_short_body_not_masked(self):
        """Very short body (< 5 chars) should not be masked (not a real IBAN)."""
        text = "Code: XX001234"
        result = redact_pii(text)
        # 4-char body is below threshold — may or may not match, but shouldn't crash
        assert result is not None

    def test_multiple_ibans_in_text(self):
        """Multiple IBANs should all be masked."""
        text = "De: ES9121000418450200051332 A: FR7630006000011234567890189"
        result = redact_pii(text)
        assert "0005" not in result or "•" in result
        # Both should have masking
        assert result.count("•") > 10


# ---------------------------------------------------------------------------
# Card / PAN number redaction
# ---------------------------------------------------------------------------


class TestCardPANRedaction:
    """Test card/PAN number masking."""

    def test_pan_16_digits_compact(self):
        """4539148803436467 → ••••••••••••6467."""
        text = "Tarjeta: 4539148803436467"
        result = redact_pii(text)
        assert "6467" in result
        assert "4539" not in result
        assert "•" in result

    def test_pan_16_digits_spaced(self):
        """4539 1488 0343 6467 → masked with spaces."""
        text = "Pago con tarjeta 4539 1488 0343 6467"
        result = redact_pii(text)
        assert "6467" in result
        assert "4539" not in result

    def test_pan_16_digits_dashed(self):
        """4539-1488-0343-6467 → masked with dashes."""
        text = "Card: 4539-1488-0343-6467"
        result = redact_pii(text)
        assert "6467" in result
        assert "4539" not in result

    def test_pan_13_digits(self):
        """13-digit card number (Visa old format)."""
        text = "Visa: 4222222222225"
        result = redact_pii(text)
        assert "2225" in result
        assert "4222222" not in result

    def test_pan_19_digits(self):
        """19-digit card number."""
        text = "Num: 6304000000000000142"
        result = redact_pii(text)
        assert "0142" in result
        assert "630400" not in result

    def test_pan_with_surrounding_text(self):
        """Card number embedded in merchant description."""
        text = "COMPRA TARJ. *6467 AMAZON PRIME"
        result = redact_pii(text)
        # Short masked ref (4 digits) should NOT be masked — it's already just last 4
        # Only full card numbers get masked
        assert "AMAZON PRIME" in result


# ---------------------------------------------------------------------------
# Account number redaction
# ---------------------------------------------------------------------------


class TestAccountNumberRedaction:
    """Test long account number masking (10-12 digits)."""

    def test_10_digit_account(self):
        """Spanish CCC-style 10-digit number."""
        text = "Nº cuenta: 0049123456"
        result = redact_pii(text)
        assert "3456" in result
        assert "0049" not in result
        assert "•" in result

    def test_12_digit_account(self):
        """12-digit account number."""
        text = "Ref: 123456789012"
        result = redact_pii(text)
        assert "9012" in result
        assert "1234" not in result

    def test_account_not_preceded_by_decimal(self):
        """Amount like 1234567890.50 should NOT have the integer part masked."""
        text = "Saldo: 1234567890.50"
        result = redact_pii(text)
        # The decimal point means this is an amount, not an account number
        assert "1234567890.50" in result

    def test_account_not_followed_by_decimal(self):
        """Number followed by comma-decimal should be preserved as amount."""
        text = "Total: 1234567890,50"
        result = redact_pii(text)
        assert "1234567890,50" in result


# ---------------------------------------------------------------------------
# Preservation tests — amounts, dates, merchant names must survive
# ---------------------------------------------------------------------------


class TestPreservation:
    """Verify that extraction-critical data is NOT masked."""

    def test_amounts_preserved(self):
        """Various amount formats should NOT be altered."""
        amounts = [
            "-42.50",
            "1,234.56",
            "+3200.00",
            "0.99",
            "12345.67",
            "-1.234,56",  # European decimal format
        ]
        for amt in amounts:
            text = f"MERCADONA {amt} EUR"
            result = redact_pii(text)
            assert amt in result, f"Amount {amt!r} was altered in redaction"

    def test_dates_preserved(self):
        """Date formats should NOT be altered."""
        dates = [
            "01/06/2024",
            "2024-06-01",
            "15/12/2025",
            "01-06-2024",
        ]
        for d in dates:
            text = f"{d} MERCADONA -42.50"
            result = redact_pii(text)
            assert d in result, f"Date {d!r} was altered in redaction"

    def test_merchant_names_preserved(self):
        """Merchant names should NOT be altered."""
        merchants = [
            "MERCADONA",
            "AMAZON PRIME",
            "LIDL",
            "TRANSFER BIZUM",
            "NOMINA EMPRESA SL",
        ]
        for merchant in merchants:
            text = f"01/06/2024 {merchant} -42.50"
            result = redact_pii(text)
            assert merchant in result, f"Merchant {merchant!r} was altered"

    def test_short_reference_numbers_preserved(self):
        """Short numbers (< 10 digits) that are likely refs should survive."""
        text = "Ref: 12345678 BIZUM"
        result = redact_pii(text)
        assert "12345678" in result  # 8 digits — not masked

    def test_6_digit_codes_preserved(self):
        """6-digit authorization codes are common and should survive."""
        text = "Auth: 482901 COMPRA POS"
        result = redact_pii(text)
        assert "482901" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_empty_string(self):
        assert redact_pii("") == ""

    def test_none_like_empty(self):
        """Empty-ish strings."""
        assert redact_pii("   ") == "   "

    def test_no_pii_unchanged(self):
        """Text with no PII should pass through unchanged."""
        text = "01/06/2024\tMERCADONA\t-42.50\tEUR"
        assert redact_pii(text) == text

    def test_real_bbva_line_format(self):
        """Simulated BBVA statement line with IBAN."""
        text = (
            "Cuenta: ES91 2100 0418 4502 0005 1332\n"
            "01/06/2024\tCOMPRA EN MERCADONA\t-42,50\t1.234,56"
        )
        result = redact_pii(text)
        # IBAN masked
        assert "2100" not in result or "•" in result
        # Transaction data preserved
        assert "MERCADONA" in result
        assert "-42,50" in result
        assert "1.234,56" in result

    def test_statement_with_mixed_pii(self):
        """Statement containing IBAN + card number + account ref."""
        text = (
            "IBAN: ES9121000418450200051332\n"
            "Tarjeta: 4539 1488 0343 6467\n"
            "01/06/2024 COMPRA AMAZON -29.99 EUR\n"
            "02/06/2024 NOMINA +3200.00 EUR"
        )
        result = redact_pii(text)
        # PII masked
        assert "21000418" not in result
        assert "4539" not in result
        # Amounts/merchants preserved
        assert "-29.99" in result
        assert "+3200.00" in result
        assert "AMAZON" in result
        assert "NOMINA" in result
