"""Deterministic import-preview quality checks.

The checks are advisory only: they never block confirmation and never call the
LLM.  They operate solely on transactions already available in preview.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from finlytics.db.repository import compute_dedup_hash

LOW_CONFIDENCE_THRESHOLD = 0.6

_SEVERITY_BY_CODE: dict[str, str] = {
    "low_confidence_category": "warning",
    "missing_category": "warning",
    "generic_category": "warning",
    "missing_merchant": "warning",
    "zero_amount": "error",
    "date_year_mismatch": "warning",
    "year_undetected": "info",
    "intra_batch_duplicate": "warning",
}

_FIELD_BY_CODE: dict[str, list[str]] = {
    "low_confidence_category": ["category"],
    "missing_category": ["category"],
    "generic_category": ["category"],
    "missing_merchant": ["merchant"],
    "zero_amount": ["amount"],
    "date_year_mismatch": ["transaction_date"],
    "intra_batch_duplicate": ["transaction_date", "amount", "description"],
}

_NON_MERCHANT_CATEGORIES = {
    "income",
    "transfers",
    "taxes",
    "bank fees",
    "cash/atm",
}

_NON_MERCHANT_DESCRIPTION_RE = re.compile(
    r"\b("
    r"salary|payroll|nomina|nómina|pension|pensión|"
    r"transfer|transferencia|traspaso|bizum|"
    r"tax|taxes|impuesto|hacienda|aeat|seguridad social|"
    r"fee|commission|comision|comisión|maintenance|mantenimiento|"
    r"atm|cash|cajero|efectivo"
    r")\b",
    re.IGNORECASE,
)


def compute_import_quality(
    transactions: Iterable[Any],
    *,
    statement_year: int | None,
    year_detected: bool,
) -> dict[str, Any]:
    """Return the advisory quality section for an import preview response."""

    txs = list(transactions)
    row_flags: list[dict[str, Any]] = []
    signal_counts: Counter[str] = Counter()

    def add_row_flag(row_index: int, code: str) -> None:
        row_flags.append(
            {
                "row_index": row_index,
                "code": code,
                "severity": _SEVERITY_BY_CODE[code],
                "fields": _FIELD_BY_CODE[code],
            }
        )
        signal_counts[code] += 1

    for idx, tx in enumerate(txs):
        category = _get(tx, "category")
        confidence = _get(tx, "category_confidence")
        amount = _get(tx, "amount")
        tx_date = _get(tx, "transaction_date")

        if confidence is not None and _as_float(confidence) < LOW_CONFIDENCE_THRESHOLD:
            add_row_flag(idx, "low_confidence_category")

        if _is_blank(category):
            add_row_flag(idx, "missing_category")
        elif _normalize_text(str(category)) == "other" and confidence is not None and _as_float(confidence) < LOW_CONFIDENCE_THRESHOLD:
            add_row_flag(idx, "generic_category")

        if _amount_is_zero_or_non_finite(amount):
            add_row_flag(idx, "zero_amount")

        if (
            statement_year is not None
            and isinstance(tx_date, date)
            and tx_date.year != statement_year
        ):
            add_row_flag(idx, "date_year_mismatch")

        if _is_blank(_get(tx, "merchant")) and _should_flag_missing_merchant(tx):
            add_row_flag(idx, "missing_merchant")

    for idx in _intra_batch_duplicate_indexes(txs):
        add_row_flag(idx, "intra_batch_duplicate")

    if not year_detected:
        signal_counts["year_undetected"] += 1

    signals = [
        {
            "code": code,
            "severity": severity,
            "count": signal_counts[code],
        }
        for code, severity in _SEVERITY_BY_CODE.items()
        if signal_counts[code] > 0
    ]

    summary_counts = {"error": 0, "warning": 0, "info": 0}
    for code, count in signal_counts.items():
        summary_counts[_SEVERITY_BY_CODE[code]] += count

    return {
        "summary": {
            "error_count": summary_counts["error"],
            "warning_count": summary_counts["warning"],
            "info_count": summary_counts["info"],
            "flagged_row_count": len({flag["row_index"] for flag in row_flags}),
        },
        "signals": signals,
        "row_flags": row_flags,
    }


def _intra_batch_duplicate_indexes(transactions: list[Any]) -> list[int]:
    seen: set[str] = set()
    duplicate_indexes: list[int] = []

    for idx, tx in enumerate(transactions):
        try:
            tx_hash = compute_dedup_hash(
                account_ref=str(_get(tx, "account_ref") or ""),
                transaction_date=_get(tx, "transaction_date"),
                amount=_as_decimal(_get(tx, "amount")),
                description=str(_get(tx, "description") or ""),
                detail=_get(tx, "detail"),
            )
        except Exception:
            continue

        if tx_hash in seen:
            duplicate_indexes.append(idx)
        else:
            seen.add(tx_hash)

    return duplicate_indexes


def _should_flag_missing_merchant(tx: Any) -> bool:
    amount = _as_decimal_or_none(_get(tx, "amount"))
    if amount is None or amount >= 0:
        return False

    category = _normalize_text(str(_get(tx, "category") or ""))
    if category in _NON_MERCHANT_CATEGORIES:
        return False

    haystack = " ".join(
        str(value or "")
        for value in (
            _get(tx, "description"),
            _get(tx, "detail"),
            _get(tx, "raw_line"),
            _get(tx, "category"),
        )
    )
    return _NON_MERCHANT_DESCRIPTION_RE.search(_strip_accents(haystack)) is None


def _get(obj: Any, field: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _as_decimal(value: Any) -> Decimal:
    decimal_value = Decimal(str(value))
    if not decimal_value.is_finite():
        raise InvalidOperation
    return decimal_value


def _as_decimal_or_none(value: Any) -> Decimal | None:
    try:
        return _as_decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _amount_is_zero_or_non_finite(value: Any) -> bool:
    amount = _as_decimal_or_none(value)
    return amount is None or amount == 0


def _normalize_text(value: str) -> str:
    return " ".join(_strip_accents(value).strip().lower().split())


def _strip_accents(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
