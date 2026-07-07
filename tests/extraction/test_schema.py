"""Tests for ExtractedTransaction schema validation."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finlytics.extraction.schema import ExtractedTransaction


def _base() -> dict:
    return {
        "transaction_date": date(2024, 6, 1),
        "amount": Decimal("-42.50"),
        "currency": "EUR",
        "description": "MERCADONA",
        "raw_line": "01/06/2024 MERCADONA -42,50 EUR",
        "category": "Groceries",
        "category_confidence": 0.95,
        "account_ref": "BBVA",
        "balance_after": Decimal("1200.00"),
    }


def test_valid_transaction():
    t = ExtractedTransaction(**_base())
    assert t.amount == Decimal("-42.50")
    assert t.currency == "EUR"
    assert t.account_ref == "BBVA"


def test_optional_fields_default_to_none():
    data = _base()
    data.pop("raw_line")
    data.pop("category_confidence")
    data.pop("balance_after")
    t = ExtractedTransaction(**data)
    assert t.raw_line is None
    assert t.category_confidence is None
    assert t.balance_after is None


def test_currency_defaults_to_eur():
    data = _base()
    data.pop("currency")
    t = ExtractedTransaction(**data)
    assert t.currency == "EUR"


def test_confidence_out_of_range_raises():
    data = _base()
    data["category_confidence"] = 1.5
    with pytest.raises(ValidationError):
        ExtractedTransaction(**data)


def test_confidence_negative_raises():
    data = _base()
    data["category_confidence"] = -0.1
    with pytest.raises(ValidationError):
        ExtractedTransaction(**data)


def test_positive_amount_income():
    data = _base()
    data["amount"] = Decimal("3200.00")
    data["category"] = "Income"
    t = ExtractedTransaction(**data)
    assert t.amount > 0
    assert t.category == "Income"


def test_proposed_category_accepted():
    data = _base()
    data["category"] = "Cosmetic Treatments"
    t = ExtractedTransaction(**data)
    assert t.category == "Cosmetic Treatments"


def test_merchant_field_optional_defaults_to_none():
    """merchant is nullable and defaults to None when omitted."""
    t = ExtractedTransaction(**_base())
    assert t.merchant is None


def test_merchant_field_accepts_brand_name():
    data = _base()
    data["merchant"] = "Mercadona"
    t = ExtractedTransaction(**data)
    assert t.merchant == "Mercadona"


def test_merchant_field_accepts_null():
    data = _base()
    data["merchant"] = None
    t = ExtractedTransaction(**data)
    assert t.merchant is None
