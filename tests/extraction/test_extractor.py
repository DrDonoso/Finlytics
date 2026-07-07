"""Tests for the extraction pipeline (LLM fully mocked — no live API calls)."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from finlytics.extraction.extractor import (
    _ExtractionResult,
    _RawTransaction,
    _normalize_tags,
    extract_transactions,
)
from finlytics.extraction.llm_client import LLMClient
from finlytics.extraction.schema import ExtractedTransaction
from finlytics.extraction.taxonomy import BASE_CATEGORIES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(transactions: list[_RawTransaction]) -> LLMClient:
    """Return an LLMClient whose .parse() returns a canned _ExtractionResult."""
    mock_inner = MagicMock()
    client = LLMClient(
        api_key="test-key",
        base_url="http://localhost",
        model="test-model",
        _client=mock_inner,
    )
    client.parse = AsyncMock(return_value=_ExtractionResult(transactions=transactions))
    return client


def _simple_raw(**kwargs) -> _RawTransaction:
    defaults = dict(
        transaction_date="2024-06-01",
        amount=-42.50,
        currency="EUR",
        description="MERCADONA",
        raw_line="01/06/2024 MERCADONA -42,50",
        category="Groceries",
        category_confidence=0.97,
        balance_after=1200.00,
    )
    defaults.update(kwargs)
    return _RawTransaction(**defaults)


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------


async def test_extract_basic_transaction():
    client = _make_client([_simple_raw()])
    result = await extract_transactions("some statement text", "BBVA", client)

    assert len(result) == 1
    t = result[0]
    assert isinstance(t, ExtractedTransaction)
    assert t.transaction_date == date(2024, 6, 1)
    assert t.amount == Decimal("-42.5")
    assert t.description == "MERCADONA"
    assert t.category == "Groceries"
    assert t.account_ref == "BBVA"
    assert t.balance_after == Decimal("1200.0")
    assert t.currency == "EUR"


async def test_extract_sets_account_ref_from_parameter():
    client = _make_client([_simple_raw()])
    result = await extract_transactions("text", "Indexa Capital", client)
    assert result[0].account_ref == "Indexa Capital"


async def test_extract_income_positive_amount():
    raw = _simple_raw(amount=3200.00, description="NOMINA EMPRESA", category="Income")
    client = _make_client([raw])
    result = await extract_transactions("nomina text", "BBVA", client)

    assert result[0].amount == Decimal("3200.0")
    assert result[0].category == "Income"


async def test_extract_multiple_transactions():
    raws = [
        _simple_raw(
            transaction_date=f"2024-06-{i:02d}",
            amount=-float(i * 10),
            description=f"Merchant {i}",
            category="Shopping",
        )
        for i in range(1, 6)
    ]
    client = _make_client(raws)
    result = await extract_transactions("multi-tx text", "BBVA", client)

    assert len(result) == 5
    assert all(isinstance(t, ExtractedTransaction) for t in result)


# ---------------------------------------------------------------------------
# Empty / guard cases
# ---------------------------------------------------------------------------


async def test_extract_empty_text_returns_empty_without_calling_llm():
    client = _make_client([])
    result = await extract_transactions("", "BBVA", client)

    assert result == []
    client.parse.assert_not_called()


async def test_extract_whitespace_only_text_returns_empty():
    client = _make_client([])
    result = await extract_transactions("   \n\t  ", "BBVA", client)

    assert result == []
    client.parse.assert_not_called()


async def test_extract_no_transactions_in_result():
    client = _make_client([])
    result = await extract_transactions("some text", "BBVA", client)
    assert result == []


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------


async def test_extract_optional_fields_none():
    raw = _simple_raw(balance_after=None, raw_line=None, category_confidence=None)
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    t = result[0]
    assert t.balance_after is None
    assert t.raw_line is None
    assert t.category_confidence is None


# ---------------------------------------------------------------------------
# Proposed / non-taxonomy categories
# ---------------------------------------------------------------------------


async def test_extract_proposed_category_is_preserved(caplog):
    raw = _simple_raw(
        description="LASER CLINIC",
        category="Cosmetic Treatments",
        is_proposed_category=True,
        category_confidence=0.60,
    )
    client = _make_client([raw])

    with caplog.at_level(logging.WARNING, logger="finlytics.extraction.extractor"):
        result = await extract_transactions("laser text", "BBVA", client)

    assert result[0].category == "Cosmetic Treatments"
    assert "Cosmetic Treatments" not in BASE_CATEGORIES
    assert any("non-taxonomy" in msg.lower() for msg in caplog.messages)


async def test_extract_all_base_categories_not_warned(caplog):
    raws = [
        _simple_raw(description=f"tx {cat}", category=cat)
        for cat in BASE_CATEGORIES
    ]
    client = _make_client(raws)

    with caplog.at_level(logging.WARNING, logger="finlytics.extraction.extractor"):
        result = await extract_transactions("text", "BBVA", client)

    assert len(result) == len(BASE_CATEGORIES)
    warning_msgs = [
        msg for msg in caplog.messages if "non-taxonomy" in msg.lower()
    ]
    assert warning_msgs == []


# ---------------------------------------------------------------------------
# _RawTransaction validation
# ---------------------------------------------------------------------------


def test_raw_transaction_invalid_date_raises():
    with pytest.raises(Exception):
        _RawTransaction(
            transaction_date="not-a-date",
            amount=-10.0,
            description="X",
            category="Other",
        )


def test_raw_transaction_confidence_bounds():
    raw = _simple_raw(category_confidence=1.0)
    assert raw.category_confidence == 1.0

    with pytest.raises(Exception):
        _simple_raw(category_confidence=1.1)


# ---------------------------------------------------------------------------
# Tag suggestion — extraction pipeline
# ---------------------------------------------------------------------------


async def test_extract_tags_passed_through():
    """Tags returned by the LLM are preserved in ExtractedTransaction."""
    raw = _simple_raw(
        description="IBERDROLA",
        category="Utilities",
        tags=["luz"],
    )
    client = _make_client([raw])
    result = await extract_transactions("iberdrola text", "BBVA", client)

    assert result[0].tags == ["luz"]


async def test_extract_tags_multiple():
    raw = _simple_raw(
        description="AGUAS DE BARCELONA",
        category="Utilities",
        tags=["agua", "suministros"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["agua", "suministros"]


async def test_extract_tags_default_empty():
    """No tags in LLM response → ExtractedTransaction.tags == []."""
    raw = _simple_raw()  # tags not supplied → defaults to []
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == []


async def test_extract_tags_all_seed_tags():
    raw = _simple_raw(
        description="VODAFONE",
        category="Utilities",
        tags=["internet", "teléfono", "gas"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["internet", "teléfono", "gas"]


# ---------------------------------------------------------------------------
# Tag normalization (_normalize_tags unit tests)
# ---------------------------------------------------------------------------


def test_normalize_tags_lowercase():
    assert _normalize_tags(["Luz", "AGUA"]) == ["luz", "agua"]


def test_normalize_tags_strip_whitespace():
    assert _normalize_tags(["  luz  ", " agua "]) == ["luz", "agua"]


def test_normalize_tags_dedupe():
    assert _normalize_tags(["luz", "Luz", "LUZ"]) == ["luz"]


def test_normalize_tags_drop_empty():
    assert _normalize_tags(["", "luz", "  "]) == ["luz"]


def test_normalize_tags_cap_at_three():
    assert _normalize_tags(["luz", "agua", "gas", "internet", "teléfono"]) == [
        "luz",
        "agua",
        "gas",
    ]


def test_normalize_tags_empty_input():
    assert _normalize_tags([]) == []


def test_normalize_tags_mixed_normalization():
    """Deduplication happens after lowercasing."""
    assert _normalize_tags(["Netflix", "  netflix  ", "GAS", "gas"]) == ["netflix", "gas"]


async def test_extract_tags_normalized_via_pipeline():
    """End-to-end: LLM returns messy tags → coerce normalises them."""
    raw = _simple_raw(
        description="IBERDROLA",
        category="Utilities",
        tags=["  Luz  ", "LUZ", "GAS", "Agua", "Internet"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    # cap at 3, lowercase, deduped: "luz" appears twice → one entry; next unique are "gas", "agua"
    assert result[0].tags == ["luz", "gas", "agua"]


# ---------------------------------------------------------------------------
# Merchant extraction — pipeline tests
# ---------------------------------------------------------------------------


async def test_extract_merchant_passed_through():
    """Merchant returned by the LLM flows onto ExtractedTransaction."""
    raw = _simple_raw(
        description="AMAZON",
        category="Shopping",
        merchant="Amazon",
    )
    client = _make_client([raw])
    result = await extract_transactions("amazon text", "BBVA", client)

    assert result[0].merchant == "Amazon"


async def test_extract_merchant_null():
    """Explicit null merchant is preserved as None on ExtractedTransaction."""
    raw = _simple_raw(
        description="TRANSFERENCIA A JUAN",
        category="Transfers",
        merchant=None,
    )
    client = _make_client([raw])
    result = await extract_transactions("transfer text", "BBVA", client)

    assert result[0].merchant is None


async def test_extract_merchant_default_none_when_not_provided():
    """When the LLM omits the merchant field it defaults to None."""
    raw = _simple_raw()  # merchant not supplied → defaults to None
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].merchant is None


async def test_extract_merchant_multi_word_brand():
    """Multi-word brand names (e.g. 'Octopus Energy') round-trip correctly."""
    raw = _simple_raw(
        description="OCTOPUS ENERGY",
        category="Utilities",
        merchant="Octopus Energy",
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].merchant == "Octopus Energy"
