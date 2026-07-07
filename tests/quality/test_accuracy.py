"""Accuracy harness — compares extracted transactions against the golden set.

compute_accuracy() is a pure helper: call it from any test or notebook.

The LIVE accuracy tests at the bottom of this file require a real LLM and are
skipped unless RUN_LLM_ACCURACY=1 AND all three OPENAI_* env vars are set.

To run the live accuracy test:

    RUN_LLM_ACCURACY=1 \\
    OPENAI_API_KEY=sk-... \\
    OPENAI_BASE_URL=https://your-litellm/v1 \\
    OPENAI_MODEL=your-model \\
    pytest tests/quality/test_accuracy.py -v

Accuracy thresholds (documented in .squad/decisions/inbox/barton-quality.md):
    - transaction_match_rate >= 0.85  (at most 2–3 misses per 15-txn golden set)
    - amount_accuracy        >= 0.90  (at most 1–2 wrong amounts per matched set)
    - category_accuracy      >= 0.75  (some ambiguity in categories is accepted)
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from finlytics.contracts import ExtractedTransaction

# ---------------------------------------------------------------------------
# Accuracy helper — pure function, no LLM, no side effects
# ---------------------------------------------------------------------------

# Maximum allowed difference to consider an amount "correct".
_AMOUNT_TOLERANCE = Decimal("0.01")

# Maximum difference in days to still attempt a match.
_DATE_WINDOW_DAYS = 0  # dates must match exactly for strict matching


def compute_accuracy(
    extracted: list[ExtractedTransaction],
    expected: list[dict],
) -> dict[str, float]:
    """Compare extracted transactions against golden expected set.

    Matching strategy: for each expected transaction, find the closest
    extracted transaction by (same date, minimum |amount| difference).
    Each extracted transaction can only be matched to one expected entry.

    Args:
        extracted: List of ExtractedTransaction returned by the pipeline.
        expected:  List of golden-set dicts (keys: transaction_date, amount,
                   currency, description, category, account_ref).

    Returns:
        Dict with three float metrics (all in range 0.0–1.0):
            transaction_match_rate  — matched / total expected
            amount_accuracy         — correctly-matched amounts / total matched
            category_accuracy       — correctly-matched categories / total matched
    """
    n_expected = len(expected)
    if n_expected == 0:
        return {
            "transaction_match_rate": 1.0,
            "amount_accuracy": 1.0,
            "category_accuracy": 1.0,
        }

    used_extracted: set[int] = set()
    matched_pairs: list[tuple[dict, ExtractedTransaction]] = []

    for exp in expected:
        exp_date = date.fromisoformat(exp["transaction_date"])
        exp_amount = Decimal(str(exp["amount"]))

        best_idx: int | None = None
        best_diff = Decimal("999999")

        for i, ext in enumerate(extracted):
            if i in used_extracted:
                continue
            if ext.transaction_date != exp_date:
                continue
            diff = abs(ext.amount - exp_amount)
            if diff < best_diff:
                best_diff = diff
                best_idx = i

        # Accept match only if the best amount is within a reasonable tolerance
        if best_idx is not None and best_diff <= Decimal("1.00"):
            used_extracted.add(best_idx)
            matched_pairs.append((exp, extracted[best_idx]))

    n_matched = len(matched_pairs)
    transaction_match_rate = n_matched / n_expected

    if not matched_pairs:
        return {
            "transaction_match_rate": transaction_match_rate,
            "amount_accuracy": 0.0,
            "category_accuracy": 0.0,
        }

    amount_correct = sum(
        1
        for exp, ext in matched_pairs
        if abs(ext.amount - Decimal(str(exp["amount"]))) <= _AMOUNT_TOLERANCE
    )
    category_correct = sum(
        1
        for exp, ext in matched_pairs
        if ext.category == exp["category"]
    )

    return {
        "transaction_match_rate": transaction_match_rate,
        "amount_accuracy": amount_correct / n_matched,
        "category_accuracy": category_correct / n_matched,
    }


# ---------------------------------------------------------------------------
# Accuracy threshold constants (documented in barton-quality.md)
# ---------------------------------------------------------------------------

THRESHOLD_MATCH_RATE = 0.85
THRESHOLD_AMOUNT_ACC = 0.90
THRESHOLD_CATEGORY_ACC = 0.75


# ---------------------------------------------------------------------------
# Unit tests for compute_accuracy itself (always run, no LLM)
# ---------------------------------------------------------------------------


def _make_ext(
    *,
    transaction_date: str,
    amount: str,
    currency: str = "EUR",
    description: str = "Test",
    category: str = "Other",
    account_ref: str = "BBVA",
) -> ExtractedTransaction:
    return ExtractedTransaction(
        transaction_date=date.fromisoformat(transaction_date),
        amount=Decimal(amount),
        currency=currency,
        description=description,
        category=category,
        account_ref=account_ref,
    )


def _make_exp(
    *,
    transaction_date: str,
    amount: str,
    currency: str = "EUR",
    description: str = "Test",
    category: str = "Other",
    account_ref: str = "BBVA",
) -> dict:
    return {
        "transaction_date": transaction_date,
        "amount": amount,
        "currency": currency,
        "description": description,
        "category": category,
        "account_ref": account_ref,
    }


def test_compute_accuracy_perfect_match():
    ext = _make_ext(transaction_date="2026-05-02", amount="-45.30", category="Groceries")
    exp = _make_exp(transaction_date="2026-05-02", amount="-45.30", category="Groceries")
    metrics = compute_accuracy([ext], [exp])
    assert metrics["transaction_match_rate"] == 1.0
    assert metrics["amount_accuracy"] == 1.0
    assert metrics["category_accuracy"] == 1.0


def test_compute_accuracy_empty_extracted():
    exp = _make_exp(transaction_date="2026-05-02", amount="-45.30")
    metrics = compute_accuracy([], [exp])
    assert metrics["transaction_match_rate"] == 0.0
    assert metrics["amount_accuracy"] == 0.0
    assert metrics["category_accuracy"] == 0.0


def test_compute_accuracy_empty_expected():
    ext = _make_ext(transaction_date="2026-05-02", amount="-45.30")
    metrics = compute_accuracy([ext], [])
    assert metrics["transaction_match_rate"] == 1.0


def test_compute_accuracy_wrong_category():
    ext = _make_ext(transaction_date="2026-05-02", amount="-45.30", category="Shopping")
    exp = _make_exp(transaction_date="2026-05-02", amount="-45.30", category="Groceries")
    metrics = compute_accuracy([ext], [exp])
    assert metrics["transaction_match_rate"] == 1.0
    assert metrics["amount_accuracy"] == 1.0
    assert metrics["category_accuracy"] == 0.0


def test_compute_accuracy_wrong_date_no_match():
    ext = _make_ext(transaction_date="2026-05-03", amount="-45.30")
    exp = _make_exp(transaction_date="2026-05-02", amount="-45.30")
    metrics = compute_accuracy([ext], [exp])
    assert metrics["transaction_match_rate"] == 0.0


def test_compute_accuracy_partial_match():
    exts = [
        _make_ext(transaction_date="2026-05-02", amount="-45.30", category="Groceries"),
        _make_ext(transaction_date="2026-05-05", amount="-78.50", category="Utilities"),
    ]
    exps = [
        _make_exp(transaction_date="2026-05-02", amount="-45.30", category="Groceries"),
        _make_exp(transaction_date="2026-05-05", amount="-78.50", category="Utilities"),
        _make_exp(transaction_date="2026-05-10", amount="-32.80", category="Dining"),
    ]
    metrics = compute_accuracy(exts, exps)
    assert metrics["transaction_match_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert metrics["amount_accuracy"] == 1.0
    assert metrics["category_accuracy"] == 1.0


def test_compute_accuracy_no_double_matching():
    """Same extracted transaction must not match two expected ones."""
    ext = _make_ext(transaction_date="2026-05-02", amount="-45.30", category="Groceries")
    exps = [
        _make_exp(transaction_date="2026-05-02", amount="-45.30", category="Groceries"),
        _make_exp(transaction_date="2026-05-02", amount="-45.30", category="Shopping"),
    ]
    metrics = compute_accuracy([ext], exps)
    # Only 1 out of 2 expected can be matched
    assert metrics["transaction_match_rate"] == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# Live LLM accuracy tests — skipped by default
# ---------------------------------------------------------------------------

_LIVE_ACCURACY_ENABLED: bool = (
    os.getenv("RUN_LLM_ACCURACY") == "1"
    and bool(os.getenv("OPENAI_API_KEY"))
    and bool(os.getenv("OPENAI_BASE_URL"))
    and bool(os.getenv("OPENAI_MODEL"))
)

_SKIP_REASON = (
    "Live LLM accuracy test skipped — set RUN_LLM_ACCURACY=1, "
    "OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL to enable."
)


@pytest.mark.skipif(not _LIVE_ACCURACY_ENABLED, reason=_SKIP_REASON)
async def test_live_accuracy_bbva(bbva_fixture_text, bbva_expected):
    """Live accuracy gate for the BBVA golden set.

    Calls the real LLM extractor (no mocking) on the BBVA synthetic fixture and
    asserts extraction quality meets the documented thresholds.

    Enabled by: RUN_LLM_ACCURACY=1 OPENAI_API_KEY=... OPENAI_BASE_URL=... OPENAI_MODEL=...
    """
    from finlytics.config import settings
    from finlytics.extraction.extractor import extract_transactions
    from finlytics.extraction.llm_client import LLMClient

    client = LLMClient.from_settings(settings)
    extracted = await extract_transactions(bbva_fixture_text, "BBVA", client)

    metrics = compute_accuracy(extracted, bbva_expected)

    assert metrics["transaction_match_rate"] >= THRESHOLD_MATCH_RATE, (
        f"BBVA match rate {metrics['transaction_match_rate']:.2%} < threshold {THRESHOLD_MATCH_RATE:.2%}"
    )
    assert metrics["amount_accuracy"] >= THRESHOLD_AMOUNT_ACC, (
        f"BBVA amount accuracy {metrics['amount_accuracy']:.2%} < threshold {THRESHOLD_AMOUNT_ACC:.2%}"
    )
    assert metrics["category_accuracy"] >= THRESHOLD_CATEGORY_ACC, (
        f"BBVA category accuracy {metrics['category_accuracy']:.2%} < threshold {THRESHOLD_CATEGORY_ACC:.2%}"
    )


@pytest.mark.skipif(not _LIVE_ACCURACY_ENABLED, reason=_SKIP_REASON)
async def test_live_accuracy_indexa(indexa_fixture_text, indexa_expected):
    """Live accuracy gate for the Indexa Capital golden set.

    Calls the real LLM extractor on the Indexa synthetic fixture and asserts
    quality meets the documented thresholds.
    """
    from finlytics.config import settings
    from finlytics.extraction.extractor import extract_transactions
    from finlytics.extraction.llm_client import LLMClient

    client = LLMClient.from_settings(settings)
    extracted = await extract_transactions(indexa_fixture_text, "Indexa Capital", client)

    metrics = compute_accuracy(extracted, indexa_expected)

    assert metrics["transaction_match_rate"] >= THRESHOLD_MATCH_RATE, (
        f"Indexa match rate {metrics['transaction_match_rate']:.2%} < threshold {THRESHOLD_MATCH_RATE:.2%}"
    )
    assert metrics["amount_accuracy"] >= THRESHOLD_AMOUNT_ACC, (
        f"Indexa amount accuracy {metrics['amount_accuracy']:.2%} < threshold {THRESHOLD_AMOUNT_ACC:.2%}"
    )
    assert metrics["category_accuracy"] >= THRESHOLD_CATEGORY_ACC, (
        f"Indexa category accuracy {metrics['category_accuracy']:.2%} < threshold {THRESHOLD_CATEGORY_ACC:.2%}"
    )
