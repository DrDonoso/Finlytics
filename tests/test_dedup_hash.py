"""Tests for compute_dedup_hash: the exact payload, normalization and components."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal

from finlytics.db.repository import compute_dedup_hash

_BASE = dict(
    account_id=1,
    transaction_date=date(2024, 1, 15),
    amount=Decimal("100.00"),
    description="NOMINA",
)


def test_no_detail_arg_equals_detail_none():
    """Calling with no detail arg is identical to detail=None."""
    assert compute_dedup_hash(**_BASE) == compute_dedup_hash(**_BASE, detail=None)


def test_payload_is_pinned():
    """Every stored key depends on this exact payload; changing it needs a re-hash migration."""
    payload = json.dumps(
        {
            "account_id": 1,
            "date": "2024-01-15",
            "amount": "100.00",
            "description": "nomina",
            "detail": "octopus energy",
        },
        sort_keys=True,
    )
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    assert compute_dedup_hash(**_BASE, detail="  OCTOPUS ENERGY ") == expected


def test_keyed_on_account_id_not_name():
    """Two accounts never share a key, whatever their names are."""
    assert compute_dedup_hash(**_BASE) != compute_dedup_hash(**{**_BASE, "account_id": 2})


def test_amount_spelling_does_not_change_hash():
    """-42.1, -42.10 and the float a JSON body carries hash alike."""
    spellings = [Decimal("-42.1"), Decimal("-42.10"), -42.1]
    hashes = {compute_dedup_hash(**{**_BASE, "amount": a}) for a in spellings}
    assert len(hashes) == 1


def test_whole_amount_spelling_does_not_change_hash():
    """-800, -800.0 (Decimal(str(float))) and the stored -800.00 hash alike."""
    spellings = [Decimal("-800"), Decimal("-800.0"), Decimal("-800.00"), -800]
    hashes = {compute_dedup_hash(**{**_BASE, "amount": a}) for a in spellings}
    assert len(hashes) == 1


def test_negative_zero_equals_zero():
    assert compute_dedup_hash(**{**_BASE, "amount": Decimal("-0")}) == compute_dedup_hash(
        **{**_BASE, "amount": Decimal("0.00")}
    )


def test_amount_rounds_half_up_like_the_column():
    """A third decimal is rounded the way Numeric(14, 2) stores it."""
    assert compute_dedup_hash(**{**_BASE, "amount": Decimal("-10.005")}) == compute_dedup_hash(
        **{**_BASE, "amount": Decimal("-10.01")}
    )
    assert compute_dedup_hash(**{**_BASE, "amount": Decimal("10.004")}) == compute_dedup_hash(
        **{**_BASE, "amount": Decimal("10.00")}
    )


def test_different_amounts_produce_different_hashes():
    assert compute_dedup_hash(**{**_BASE, "amount": Decimal("-42.10")}) != compute_dedup_hash(
        **{**_BASE, "amount": Decimal("-42.11")}
    )


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


def test_different_disambiguators_produce_different_hashes():
    """Different force-import disambiguators produce different 64-char digests."""
    h1 = compute_dedup_hash(**_BASE, disambiguator="force-1")
    h2 = compute_dedup_hash(**_BASE, disambiguator="force-2")

    assert h1 != h2
    assert len(h1) == 64
    assert len(h2) == 64


def test_same_disambiguator_same_hash():
    """The same disambiguator is stable for deterministic tests and retries."""
    h1 = compute_dedup_hash(**_BASE, disambiguator="force-1")
    h2 = compute_dedup_hash(**_BASE, disambiguator="force-1")
    assert h1 == h2
