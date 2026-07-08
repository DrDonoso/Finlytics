"""Tests for compute_dedup_hash: backward compatibility + detail component."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finlytics.db.repository import compute_dedup_hash

_BASE = dict(
    account_ref="BBVA",
    transaction_date=date(2024, 1, 15),
    amount=Decimal("100.00"),
    description="NOMINA",
)


def test_no_detail_arg_equals_detail_none():
    """Calling with no detail arg is identical to detail=None."""
    assert compute_dedup_hash(**_BASE) == compute_dedup_hash(**_BASE, detail=None)


def test_empty_string_detail_equals_no_detail():
    """detail='' produces the same hash as omitting detail (backward-compat)."""
    assert compute_dedup_hash(**_BASE) == compute_dedup_hash(**_BASE, detail="")


def test_detail_whitespace_only_equals_no_detail():
    """detail containing only whitespace is treated as absent."""
    assert compute_dedup_hash(**_BASE) == compute_dedup_hash(**_BASE, detail="   ")


def test_detail_changes_hash():
    """A non-empty detail value produces a different hash than no detail."""
    h_no_detail = compute_dedup_hash(**_BASE)
    h_with_detail = compute_dedup_hash(**_BASE, detail="OCTOPUS ENERGY")
    assert h_no_detail != h_with_detail


def test_different_details_produce_different_hashes():
    """Two transactions identical except for detail → different hashes."""
    h1 = compute_dedup_hash(**_BASE, detail="OCTOPUS ENERGY")
    h2 = compute_dedup_hash(**_BASE, detail="GOOGLE CLOUD")
    assert h1 != h2


def test_same_detail_same_hash():
    """Same inputs including detail always produce the same hash (deterministic)."""
    h1 = compute_dedup_hash(**_BASE, detail="OCTOPUS ENERGY")
    h2 = compute_dedup_hash(**_BASE, detail="OCTOPUS ENERGY")
    assert h1 == h2


def test_detail_case_insensitive():
    """detail matching is case-insensitive (normalised to lowercase before hashing)."""
    h_lower = compute_dedup_hash(**_BASE, detail="octopus energy")
    h_upper = compute_dedup_hash(**_BASE, detail="OCTOPUS ENERGY")
    assert h_lower == h_upper


def test_detail_stripped_whitespace():
    """Leading/trailing whitespace in detail is stripped before hashing."""
    h1 = compute_dedup_hash(**_BASE, detail="OCTOPUS ENERGY")
    h2 = compute_dedup_hash(**_BASE, detail="  OCTOPUS ENERGY  ")
    assert h1 == h2
