"""Golden-set pipeline tests — mocked LLM, zero live API calls.

For each synthetic fixture (BBVA, Indexa Capital):
  1. Feed the raw statement text to extract_transactions() with a mocked LLMClient.
  2. Assert the returned ExtractedTransaction list matches the hand-labeled expected JSON
     (dates, signed amounts, currency, description, category, account_ref, balance_after).
  3. Assert that PII (IBAN, card number) is masked in the text that reaches the LLM.

These tests validate the deterministic wiring of the pipeline end-to-end without
calling the real LLM or needing any credentials.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from finlytics.extraction.extractor import (
    _ExtractionResult,
    _RawTransaction,
    extract_transactions,
)
from finlytics.extraction.llm_client import LLMClient
from finlytics.extraction.schema import ExtractedTransaction


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_client_from_expected(expected: list[dict]) -> LLMClient:
    """Build a mocked LLMClient that returns a canned _ExtractionResult.

    The canned response is derived from the golden expected JSON so that the
    pipeline wiring, type coercions, and account_ref injection can all be
    validated end-to-end without a live LLM.
    """
    raws = [
        _RawTransaction(
            transaction_date=item["transaction_date"],
            amount=float(item["amount"]),
            currency=item.get("currency", "EUR"),
            description=item["description"],
            raw_line=item.get("raw_line"),
            category=item["category"],
            category_confidence=item.get("category_confidence"),
            balance_after=(
                float(item["balance_after"])
                if item.get("balance_after") is not None
                else None
            ),
        )
        for item in expected
    ]
    mock_inner = MagicMock()
    client = LLMClient(
        api_key="test-key",
        base_url="http://localhost",
        model="test-model",
        _client=mock_inner,
    )
    client.parse = AsyncMock(return_value=_ExtractionResult(transactions=raws))
    return client


def _assert_matches_expected(
    result: list[ExtractedTransaction],
    expected: list[dict],
) -> None:
    """Assert each extracted transaction matches the golden expected entry."""
    assert len(result) == len(expected), (
        f"Expected {len(expected)} transactions, got {len(result)}"
    )
    for i, (actual, exp) in enumerate(zip(result, expected)):
        assert actual.transaction_date == date.fromisoformat(exp["transaction_date"]), (
            f"[{i}] transaction_date: {actual.transaction_date!r} != {exp['transaction_date']!r}"
        )
        assert actual.amount == Decimal(str(exp["amount"])), (
            f"[{i}] amount: {actual.amount!r} != {exp['amount']!r}"
        )
        assert actual.currency == exp["currency"], (
            f"[{i}] currency: {actual.currency!r} != {exp['currency']!r}"
        )
        assert actual.description == exp["description"], (
            f"[{i}] description: {actual.description!r} != {exp['description']!r}"
        )
        assert actual.category == exp["category"], (
            f"[{i}] category: {actual.category!r} != {exp['category']!r}"
        )
        assert actual.account_ref == exp["account_ref"], (
            f"[{i}] account_ref: {actual.account_ref!r} != {exp['account_ref']!r}"
        )
        if exp.get("balance_after") is not None:
            assert actual.balance_after == Decimal(str(exp["balance_after"])), (
                f"[{i}] balance_after: {actual.balance_after!r} != {exp['balance_after']!r}"
            )


# ===========================================================================
# BBVA golden-set pipeline tests
# ===========================================================================


async def test_bbva_golden_pipeline_full_match(bbva_fixture_text, bbva_expected):
    """Full pipeline wiring: BBVA text → redact_pii → mocked LLM → ExtractedTransaction.

    Validates that the pipeline assembles the correct ExtractedTransaction objects
    for all 10 BBVA transactions, including correct types (date, Decimal, str).
    """
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)
    _assert_matches_expected(result, bbva_expected)


async def test_bbva_golden_transaction_count(bbva_fixture_text, bbva_expected):
    """BBVA fixture must yield exactly 10 transactions."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)
    assert len(result) == 10


async def test_bbva_golden_income_salary(bbva_fixture_text, bbva_expected):
    """Salary (nómina) must be positive amount, category=Income."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)

    income = [t for t in result if t.category == "Income"]
    assert len(income) == 1, "Expected exactly one Income transaction"
    nomina = income[0]
    assert nomina.amount == Decimal("2850.00")
    assert nomina.transaction_date == date(2026, 5, 15)
    assert nomina.currency == "EUR"


async def test_bbva_golden_refund_is_positive(bbva_fixture_text, bbva_expected):
    """Amazon devolution/refund must have a positive amount (money in)."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)

    refund = next(
        (t for t in result if "DEVOLUCION" in t.description.upper()),
        None,
    )
    assert refund is not None, "Refund transaction not found"
    assert refund.amount > Decimal("0"), "Refund must be a positive (credit) amount"
    assert refund.amount == Decimal("29.99")
    assert refund.transaction_date == date(2026, 5, 18)


async def test_bbva_golden_foreign_currency_usd(bbva_fixture_text, bbva_expected):
    """Foreign-currency purchase must have currency='USD', negative amount."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)

    foreign = [t for t in result if t.currency == "USD"]
    assert len(foreign) == 1, "Expected exactly one USD transaction"
    assert foreign[0].amount == Decimal("-25.00")
    assert foreign[0].transaction_date == date(2026, 5, 20)


async def test_bbva_golden_bank_fee(bbva_fixture_text, bbva_expected):
    """Maintenance commission must be category=Bank Fees, negative amount."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)

    fees = [t for t in result if t.category == "Bank Fees"]
    assert len(fees) == 1, "Expected exactly one Bank Fees transaction"
    assert fees[0].amount == Decimal("-4.00")
    assert fees[0].transaction_date == date(2026, 5, 22)


async def test_bbva_golden_groceries_both_stores(bbva_fixture_text, bbva_expected):
    """Mercadona and Lidl must both be Groceries (not Shopping)."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)

    groceries = [t for t in result if t.category == "Groceries"]
    assert len(groceries) == 2, "Expected two Groceries transactions (Mercadona + Lidl)"
    descs = {t.description for t in groceries}
    assert any("MERCADONA" in d for d in descs)
    assert any("LIDL" in d for d in descs)


async def test_bbva_golden_utilities_count(bbva_fixture_text, bbva_expected):
    """Endesa and Naturgy bills must both be Utilities."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)

    utilities = [t for t in result if t.category == "Utilities"]
    assert len(utilities) == 2


async def test_bbva_golden_balance_after_coercion(bbva_fixture_text, bbva_expected):
    """Running balance must be coerced to Decimal correctly."""
    client = _make_client_from_expected(bbva_expected)
    result = await extract_transactions(bbva_fixture_text, "BBVA", client)

    # First transaction — saldo 1404.70
    assert result[0].balance_after == Decimal("1404.70")
    # Salary transaction — saldo 4083.40
    salary_txn = next(t for t in result if t.category == "Income")
    assert salary_txn.balance_after == Decimal("4083.40")


# ---------------------------------------------------------------------------
# BBVA redaction cross-check tests
# ---------------------------------------------------------------------------


async def test_bbva_iban_masked_before_llm(bbva_fixture_text, bbva_expected):
    """IBAN ES49 0182 6370 8002 0151 3307 must be masked in the user prompt.

    The LLM must NOT see raw IBAN digits; only the country code + last 4 survive.
    """
    client = _make_client_from_expected(bbva_expected)
    await extract_transactions(bbva_fixture_text, "BBVA", client)

    user_prompt: str = client.parse.call_args.kwargs["user"]
    assert "ES49" in user_prompt, "IBAN country code must be preserved"
    assert "0182" not in user_prompt, "IBAN body must be masked"
    assert "3307" in user_prompt, "IBAN last 4 must be preserved"
    assert "\u2022" in user_prompt, "Masking bullet character must be present"


async def test_bbva_card_masked_before_llm(bbva_fixture_text, bbva_expected):
    """Card 4532 0151 1283 3467 must be masked; only last 4 digits (3467) survive."""
    client = _make_client_from_expected(bbva_expected)
    await extract_transactions(bbva_fixture_text, "BBVA", client)

    user_prompt: str = client.parse.call_args.kwargs["user"]
    assert "4532" not in user_prompt, "Card prefix must be masked"
    assert "3467" in user_prompt, "Card last 4 must be preserved"


async def test_bbva_llm_receives_system_prompt(bbva_fixture_text, bbva_expected):
    """The mocked LLM must receive both system and user prompts."""
    client = _make_client_from_expected(bbva_expected)
    await extract_transactions(bbva_fixture_text, "BBVA", client)

    call_kwargs = client.parse.call_args.kwargs
    assert "system" in call_kwargs
    assert "BBVA" in call_kwargs["system"], "account_ref must appear in system prompt"
    assert "user" in call_kwargs


# ===========================================================================
# Indexa Capital golden-set pipeline tests
# ===========================================================================


async def test_indexa_golden_pipeline_full_match(indexa_fixture_text, indexa_expected):
    """Full pipeline wiring: Indexa text → redact_pii → mocked LLM → ExtractedTransaction.

    Validates pipeline assembly for all 5 Indexa transactions.
    """
    client = _make_client_from_expected(indexa_expected)
    result = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)
    _assert_matches_expected(result, indexa_expected)


async def test_indexa_golden_transaction_count(indexa_fixture_text, indexa_expected):
    """Indexa fixture must yield exactly 5 transactions."""
    client = _make_client_from_expected(indexa_expected)
    result = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)
    assert len(result) == 5


async def test_indexa_golden_investment_contribution(indexa_fixture_text, indexa_expected):
    """Contribution (aportación) must be category=Investments with a POSITIVE amount (money into portfolio)."""
    client = _make_client_from_expected(indexa_expected)
    result = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    investments = [t for t in result if t.category == "Investments"]
    assert len(investments) == 1
    contribution = investments[0]
    assert contribution.amount == Decimal("500.00"), "Contribution (aportación) must be positive"
    assert contribution.transaction_date == date(2026, 5, 5)
    assert contribution.currency == "EUR"


async def test_indexa_golden_management_fee(indexa_fixture_text, indexa_expected):
    """Indexa management commission must be Bank Fees, negative amount."""
    client = _make_client_from_expected(indexa_expected)
    result = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    fees = [t for t in result if t.category == "Bank Fees"]
    assert len(fees) == 1
    assert fees[0].amount == Decimal("-3.25")
    assert fees[0].transaction_date == date(2026, 5, 12)


async def test_indexa_golden_income_dividend_and_interest(indexa_fixture_text, indexa_expected):
    """Dividend and interest must both be Income; amounts 12.50 and 8.75."""
    client = _make_client_from_expected(indexa_expected)
    result = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    income = [t for t in result if t.category == "Income"]
    assert len(income) == 2, "Expected dividend + interest = 2 Income transactions"
    amounts = sorted(t.amount for t in income)
    assert amounts == [Decimal("8.75"), Decimal("12.50")]


async def test_indexa_golden_transfer_out(indexa_fixture_text, indexa_expected):
    """Transfer to BBVA must be category=Transfers, negative amount -200.00."""
    client = _make_client_from_expected(indexa_expected)
    result = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    transfers = [t for t in result if t.category == "Transfers"]
    assert len(transfers) == 1
    assert transfers[0].amount == Decimal("-200.00")
    assert transfers[0].transaction_date == date(2026, 5, 28)


async def test_indexa_golden_account_ref_injected(indexa_fixture_text, indexa_expected):
    """All Indexa transactions must have account_ref='Indexa Capital'."""
    client = _make_client_from_expected(indexa_expected)
    result = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    assert all(t.account_ref == "Indexa Capital" for t in result)


# ---------------------------------------------------------------------------
# Indexa redaction cross-check tests
# ---------------------------------------------------------------------------


async def test_indexa_own_iban_masked_before_llm(indexa_fixture_text, indexa_expected):
    """Indexa account IBAN ES76 0487 0500 5100 0503 8471 must be masked.

    Body digits must be replaced with bullet characters; last 4 (8471) survive.
    """
    client = _make_client_from_expected(indexa_expected)
    await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    user_prompt: str = client.parse.call_args.kwargs["user"]
    assert "ES76" in user_prompt, "IBAN country code must be preserved"
    assert "0487" not in user_prompt, "Indexa IBAN body must be masked"
    assert "8471" in user_prompt, "Indexa IBAN last 4 must be preserved"
    assert "\u2022" in user_prompt


async def test_indexa_transfer_bbva_iban_masked_before_llm(indexa_fixture_text, indexa_expected):
    """BBVA IBAN in the transfer line (ES49 0182...) must also be masked."""
    client = _make_client_from_expected(indexa_expected)
    await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    user_prompt: str = client.parse.call_args.kwargs["user"]
    assert "0182" not in user_prompt, "BBVA IBAN body in transfer line must be masked"
    assert "3307" in user_prompt, "BBVA IBAN last 4 must be preserved"


async def test_indexa_llm_receives_indexa_capital_account_ref(
    indexa_fixture_text, indexa_expected
):
    """System prompt must reference 'Indexa Capital' as account_ref."""
    client = _make_client_from_expected(indexa_expected)
    await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    system_prompt: str = client.parse.call_args.kwargs["system"]
    assert "Indexa Capital" in system_prompt


# ===========================================================================
# PDF parser integration test
# ===========================================================================


async def test_pdf_parser_extracts_key_data(bbva_pdf_bytes):
    """parse_statement() on the generated BBVA PDF must return text with key data.

    Exercises the pdfplumber path in parser.py using a programmatically
    generated synthetic PDF (no real statement needed).
    """
    from finlytics.extraction.parser import parse_statement

    text = parse_statement(bbva_pdf_bytes, file_type="pdf")

    assert text.strip(), "PDF parser must return non-empty text"
    assert "MERCADONA" in text, "Grocery transaction must be present in parsed text"
    assert "NOMINA" in text, "Salary transaction must be present in parsed text"
    assert "REPSOL" in text, "Fuel transaction must be present in parsed text"
    # Amounts must survive parsing
    assert any(ch.isdigit() for ch in text), "Parsed PDF must contain numeric data"
