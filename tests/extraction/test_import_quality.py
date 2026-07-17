from __future__ import annotations

from datetime import date
from decimal import Decimal

from finlytics.contracts import ExtractedTransaction
from finlytics.extraction.import_quality import compute_import_quality


def _tx(**overrides) -> ExtractedTransaction:
    data = {
        "transaction_date": date(2024, 6, 1),
        "amount": Decimal("-12.34"),
        "currency": "EUR",
        "description": "Mercadona compra",
        "category": "Groceries",
        "category_confidence": 0.95,
        "account_ref": "BBVA",
        "merchant": "Mercadona",
    }
    data.update(overrides)
    return ExtractedTransaction(**data)


def _quality(transactions, *, statement_year=2024, year_detected=True):
    return compute_import_quality(
        transactions,
        statement_year=statement_year,
        year_detected=year_detected,
    )


def _codes(quality):
    return [signal["code"] for signal in quality["signals"]]


def _signal_count(quality, code):
    return next(signal["count"] for signal in quality["signals"] if signal["code"] == code)


def _row_flags(quality, code):
    return [flag for flag in quality["row_flags"] if flag["code"] == code]


def test_low_confidence_category_below_threshold_is_warning():
    quality = _quality([_tx(category_confidence=0.59)])

    assert _signal_count(quality, "low_confidence_category") == 1
    assert _row_flags(quality, "low_confidence_category") == [
        {
            "row_index": 0,
            "code": "low_confidence_category",
            "severity": "warning",
            "fields": ["category"],
        }
    ]


def test_low_confidence_threshold_boundary_is_not_flagged():
    quality = _quality([_tx(category_confidence=0.6), _tx(category_confidence=None)])

    assert "low_confidence_category" not in _codes(quality)


def test_missing_category_is_flagged_even_without_confidence():
    null_category = _tx(category_confidence=None).model_dump()
    null_category["category"] = None
    quality = _quality([_tx(category="", category_confidence=None), null_category])

    assert _signal_count(quality, "missing_category") == 2
    assert _row_flags(quality, "missing_category")[0]["fields"] == ["category"]


def test_generic_other_category_only_flagged_when_low_confidence():
    quality = _quality(
        [
            _tx(category="Other", category_confidence=0.59),
            _tx(category="Other", category_confidence=0.6),
            _tx(category="Other", category_confidence=None),
        ]
    )

    assert _signal_count(quality, "generic_category") == 1
    assert _row_flags(quality, "generic_category")[0]["row_index"] == 0


def test_zero_amount_is_error_but_non_blocking_summary_signal():
    non_finite_amount = _tx().model_dump()
    non_finite_amount["amount"] = "NaN"
    quality = _quality([_tx(amount=Decimal("0.00")), non_finite_amount])

    assert _signal_count(quality, "zero_amount") == 2
    assert _row_flags(quality, "zero_amount")[0]["severity"] == "error"
    assert quality["summary"]["error_count"] == 2


def test_date_year_mismatch_uses_statement_year_when_present():
    quality = _quality([_tx(transaction_date=date(2023, 12, 31))], statement_year=2024)

    assert _signal_count(quality, "date_year_mismatch") == 1
    assert _row_flags(quality, "date_year_mismatch")[0]["fields"] == ["transaction_date"]


def test_date_year_mismatch_not_checked_when_statement_year_missing():
    quality = _quality([_tx(transaction_date=date(2023, 12, 31))], statement_year=None)

    assert "date_year_mismatch" not in _codes(quality)


def test_year_undetected_is_file_level_info_without_row_flag():
    quality = _quality([_tx()], statement_year=None, year_detected=False)

    assert _signal_count(quality, "year_undetected") == 1
    assert not _row_flags(quality, "year_undetected")
    assert quality["summary"]["info_count"] == 1
    assert quality["summary"]["flagged_row_count"] == 0


def test_missing_merchant_flags_expense_card_like_rows_only():
    quality = _quality([_tx(merchant=None, description="Pago tarjeta supermercado")])

    assert _signal_count(quality, "missing_merchant") == 1
    assert _row_flags(quality, "missing_merchant")[0]["fields"] == ["merchant"]


def test_missing_merchant_does_not_flag_legitimate_non_merchant_rows():
    transactions = [
        _tx(amount=Decimal("2500.00"), category="Income", description="Nómina julio", merchant=None),
        _tx(category="Transfers", description="Transferencia entre cuentas", merchant=None),
        _tx(category="Taxes", description="Pago impuesto AEAT", merchant=None),
        _tx(category="Bank Fees", description="Comisión mantenimiento cuenta", merchant=None),
        _tx(category="Cash/ATM", description="Retirada cajero", merchant=None),
        _tx(category="Other", description="Bizum transferencia familiar", merchant=None),
    ]

    quality = _quality(transactions)

    assert "missing_merchant" not in _codes(quality)


def test_intra_batch_duplicate_flags_second_and_later_occurrences():
    duplicate = _tx(description="Mercadona compra", merchant="Mercadona")
    quality = _quality([duplicate, duplicate.model_copy(), duplicate.model_copy()])

    assert _signal_count(quality, "intra_batch_duplicate") == 2
    assert [flag["row_index"] for flag in _row_flags(quality, "intra_batch_duplicate")] == [1, 2]


def test_intra_batch_duplicate_uses_detail_in_hash_inputs():
    quality = _quality(
        [
            _tx(description="Adeudo a su cargo", detail="Octopus Energy"),
            _tx(description="Adeudo a su cargo", detail="Google Cloud"),
        ]
    )

    assert "intra_batch_duplicate" not in _codes(quality)


def test_summary_counts_and_flagged_row_count_are_deterministic():
    quality = _quality(
        [
            _tx(category_confidence=0.59, merchant=None),
            _tx(amount=Decimal("0.00"), category="", merchant=""),
        ],
        statement_year=None,
        year_detected=False,
    )

    assert quality["summary"] == {
        "error_count": 1,
        "warning_count": 3,
        "info_count": 1,
        "flagged_row_count": 2,
    }
    assert [signal["code"] for signal in quality["signals"]] == [
        "low_confidence_category",
        "missing_category",
        "missing_merchant",
        "zero_amount",
        "year_undetected",
    ]
