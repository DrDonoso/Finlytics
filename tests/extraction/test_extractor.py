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
    _drop_category_tags,
    _drop_merchant_tags,
    _normalize_tags,
    extract_transactions,
)
from finlytics.extraction.llm_client import LLMClient
from finlytics.extraction.schema import ExtractedTransaction
from finlytics.extraction.taxonomy import BASE_CATEGORIES, BASE_CATEGORY_ES


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
        tags=["agua", "factura"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["agua", "factura"]


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


# ---------------------------------------------------------------------------
# Merchant-tag safety guard — pipeline tests
# ---------------------------------------------------------------------------


async def test_merchant_tag_guard_removes_tag_equal_to_merchant():
    """Guard drops a tag that equals the merchant name (case-insensitive)."""
    raw = _simple_raw(
        description="MERCADONA",
        category="Groceries",
        merchant="Mercadona",
        tags=["mercadona", "ahorro"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].merchant == "Mercadona"
    assert result[0].tags == ["ahorro"]


async def test_merchant_tag_guard_keeps_unrelated_tags():
    """Only merchant-matching tags are removed; unrelated tags survive."""
    raw = _simple_raw(
        description="NETFLIX",
        category="Entertainment",
        merchant="Netflix",
        tags=["netflix", "streaming", "suscripción"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["streaming", "suscripción"]


async def test_merchant_tag_guard_with_leading_emoji():
    """Guard strips a leading emoji before comparing against the merchant."""
    raw = _simple_raw(
        description="ZARA",
        category="Shopping",
        merchant="Zara",
        tags=["🛍zara", "moda"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["moda"]


async def test_merchant_tag_guard_merchant_none_no_drop():
    """When merchant is None, all tags are preserved unchanged."""
    raw = _simple_raw(
        description="TRANSFERENCIA",
        category="Transfers",
        merchant=None,
        tags=["luz", "gas"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["luz", "gas"]


# ---------------------------------------------------------------------------
# _drop_merchant_tags unit tests
# ---------------------------------------------------------------------------


def test_drop_merchant_tags_removes_exact_match():
    assert _drop_merchant_tags(["mercadona", "compras"], "Mercadona") == ["compras"]


def test_drop_merchant_tags_merchant_none_noop():
    assert _drop_merchant_tags(["luz", "gas"], None) == ["luz", "gas"]


def test_drop_merchant_tags_emoji_stripped():
    assert _drop_merchant_tags(["🛍zara", "moda"], "Zara") == ["moda"]


def test_drop_merchant_tags_keeps_unrelated():
    assert _drop_merchant_tags(["netflix", "ocio", "suscripción"], "Netflix") == [
        "ocio",
        "suscripción",
    ]


def test_drop_merchant_tags_all_removed():
    """All tags dropped when every one matches the merchant (tags pre-normalized to lowercase)."""
    assert _drop_merchant_tags(["amazon"], "Amazon") == []


def test_drop_merchant_tags_empty_input():
    assert _drop_merchant_tags([], "Amazon") == []


# ---------------------------------------------------------------------------
# Category-name tag guard — _drop_category_tags unit tests
# ---------------------------------------------------------------------------


def test_drop_category_tags_english_base_category():
    """English base category name is dropped regardless of the row category."""
    assert _drop_category_tags(["housing", "préstamo"], "Housing") == ["préstamo"]


def test_drop_category_tags_spanish_label():
    """Spanish label for a base category is dropped (vivienda = Housing)."""
    assert _drop_category_tags(["vivienda", "préstamo"], "Housing") == ["préstamo"]


def test_drop_category_tags_row_category_custom():
    """Tag matching a custom/proposed category (not in base list) is dropped."""
    assert _drop_category_tags(["cosmetic treatments", "láser"], "Cosmetic Treatments") == [
        "láser"
    ]


def test_drop_category_tags_keeps_specific_tags():
    """Specific sub-category tags (luz, agua, mascotas) are never dropped."""
    assert _drop_category_tags(["luz", "agua"], "Utilities") == ["luz", "agua"]
    assert _drop_category_tags(["mascotas"], "Shopping") == ["mascotas"]


def test_drop_category_tags_all_es_labels_are_forbidden():
    """Every Spanish label is forbidden as a tag (spot-check a variety)."""
    forbidden_es = ["alimentación", "restaurantes", "transporte", "combustible",
                    "suministros", "seguros", "compras", "ocio", "suscripciones",
                    "viajes", "educación", "ingresos", "transferencias", "inversiones",
                    "comisiones bancarias", "impuestos", "efectivo/cajero", "otros"]
    for label in forbidden_es:
        assert _drop_category_tags([label, "luz"], "Other") == ["luz"], (
            f"Expected '{label}' to be dropped as a forbidden category label"
        )


def test_drop_category_tags_all_en_names_are_forbidden():
    """Every English base category name is forbidden as a tag."""
    for cat in BASE_CATEGORIES:
        tag = cat.lower()
        assert _drop_category_tags([tag, "luz"], "Other") == ["luz"], (
            f"Expected '{tag}' to be dropped as a forbidden English category name"
        )


def test_drop_category_tags_emoji_prefix_dropped():
    """Leading emoji is stripped before category comparison."""
    assert _drop_category_tags(["🏠vivienda", "préstamo"], "Housing") == ["préstamo"]


def test_drop_category_tags_empty_input():
    assert _drop_category_tags([], "Housing") == []


# ---------------------------------------------------------------------------
# Category-name tag guard — pipeline tests (LLM mocked)
# ---------------------------------------------------------------------------


async def test_pipeline_drops_spanish_category_label_tag():
    """LLM tag 'vivienda' (= ES label for Housing) is dropped post-process."""
    raw = _simple_raw(
        description="HIPOTECA BBVA",
        category="Housing",
        merchant=None,
        tags=["vivienda", "préstamo"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert "vivienda" not in result[0].tags
    assert result[0].tags == ["préstamo"]


async def test_pipeline_drops_english_category_name_tag():
    """LLM tag 'housing' (= EN category name) is dropped post-process."""
    raw = _simple_raw(
        description="HIPOTECA BBVA",
        category="Housing",
        merchant=None,
        tags=["housing", "comunidad"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert "housing" not in result[0].tags
    assert result[0].tags == ["comunidad"]


async def test_pipeline_drops_row_category_as_tag():
    """LLM tag equal to the transaction's own category (lowercased) is dropped."""
    raw = _simple_raw(
        description="MERCADONA",
        category="Groceries",
        merchant="Mercadona",
        tags=["groceries", "alimentación", "fruta"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["fruta"]


async def test_pipeline_unrelated_tags_survive_category_guard():
    """Tags that are not category names (luz, mascotas, préstamo) survive intact."""
    raw = _simple_raw(
        description="IBERDROLA",
        category="Utilities",
        merchant="Iberdrola",
        tags=["luz", "mascotas"],
    )
    client = _make_client([raw])
    result = await extract_transactions("text", "BBVA", client)

    assert result[0].tags == ["luz", "mascotas"]


async def test_pipeline_base_category_es_covers_all_20():
    """BASE_CATEGORY_ES has exactly one entry per base category."""
    assert set(BASE_CATEGORY_ES.keys()) == set(BASE_CATEGORIES)
    assert len(BASE_CATEGORY_ES) == len(BASE_CATEGORIES)
