"""Tests for Transaction.detail persistence and dedup correctness.

These tests verify:
- Transaction and Rule ORM models carry the expected nullable columns.
- upsert_transactions passes detail to the INSERT values and dedup hash.
- A detail-less ExtractedTransaction hashes identically to pre-Wave-2 behaviour.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from finlytics.contracts import ExtractedTransaction
from finlytics.db.repository import compute_dedup_hash, upsert_transactions


# ── ORM model column checks ───────────────────────────────────────────────────

def test_transaction_model_has_detail_column():
    """Transaction.detail column exists and is nullable."""
    from finlytics.db.models import Transaction
    col = Transaction.__table__.c["detail"]
    assert col is not None
    assert col.nullable is True


def test_rule_model_has_detail_mode_column():
    """Rule.detail_mode column exists and is nullable."""
    from finlytics.db.models import Rule
    col = Rule.__table__.c["detail_mode"]
    assert col is not None
    assert col.nullable is True


def test_rule_model_has_detail_value_column():
    """Rule.detail_value column exists and is nullable."""
    from finlytics.db.models import Rule
    col = Rule.__table__.c["detail_value"]
    assert col is not None
    assert col.nullable is True


# ── upsert_transactions persists detail ──────────────────────────────────────

async def test_upsert_passes_detail_to_insert_values():
    """upsert_transactions includes detail in the INSERT values dict."""
    tx = ExtractedTransaction(
        transaction_date=date(2024, 6, 1),
        amount=Decimal("-42.50"),
        currency="EUR",
        description="ADEUDOASUCARGO",
        category="Energy",
        account_ref="BBVA",
        detail="GCREOCTOPUSENERGY",
    )
    expected_hash = compute_dedup_hash(
        "BBVA", date(2024, 6, 1), Decimal("-42.50"), "ADEUDOASUCARGO",
        detail="GCREOCTOPUSENERGY",
    )

    captured: dict = {}
    fake_run = MagicMock(id=1, account_id=1)
    category_mock = MagicMock(id=5)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = 1
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    def fake_pg_insert(table):
        stmt = MagicMock()
        def capture(**kw):
            captured.update(kw)
            return stmt
        stmt.values = MagicMock(side_effect=capture)
        stmt.on_conflict_do_nothing = MagicMock(return_value=stmt)
        stmt.returning = MagicMock(return_value=stmt)
        return stmt

    with patch("finlytics.db.repository.get_or_create_category", new_callable=AsyncMock,
               return_value=category_mock):
        with patch("finlytics.db.repository.pg_insert", side_effect=fake_pg_insert):
            n_ins, n_dup = await upsert_transactions(session, fake_run, [tx])

    assert n_ins == 1
    assert captured["detail"] == "GCREOCTOPUSENERGY"
    assert captured["dedup_hash"] == expected_hash


async def test_upsert_detail_less_tx_hash_unchanged():
    """A detail-less ExtractedTransaction produces the same hash as before Wave 2."""
    tx = ExtractedTransaction(
        transaction_date=date(2024, 6, 1),
        amount=Decimal("-42.50"),
        currency="EUR",
        description="MERCADONA",
        category="Groceries",
        account_ref="BBVA",
        # detail intentionally absent (default None)
    )
    # Pre-Wave-2 formula: no detail component
    legacy_hash = compute_dedup_hash(
        "BBVA", date(2024, 6, 1), Decimal("-42.50"), "MERCADONA",
    )

    captured: dict = {}
    fake_run = MagicMock(id=1, account_id=1)
    category_mock = MagicMock(id=5)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # duplicate
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    def fake_pg_insert(table):
        stmt = MagicMock()
        def capture(**kw):
            captured.update(kw)
            return stmt
        stmt.values = MagicMock(side_effect=capture)
        stmt.on_conflict_do_nothing = MagicMock(return_value=stmt)
        stmt.returning = MagicMock(return_value=stmt)
        return stmt

    with patch("finlytics.db.repository.get_or_create_category", new_callable=AsyncMock,
               return_value=category_mock):
        with patch("finlytics.db.repository.pg_insert", side_effect=fake_pg_insert):
            await upsert_transactions(session, fake_run, [tx])

    assert captured["dedup_hash"] == legacy_hash
    assert captured["detail"] is None


async def test_upsert_skips_existing_duplicate_by_default_but_forced_duplicate_inserts():
    """allow_duplicate controls whether an existing dedup_hash conflict is bypassed."""
    tx = ExtractedTransaction(
        transaction_date=date(2024, 6, 1),
        amount=Decimal("-42.50"),
        currency="EUR",
        description="MERCADONA",
        category="Groceries",
        account_ref="BBVA",
    )
    forced_tx = tx.model_copy(update={"allow_duplicate": True})
    natural_hash = compute_dedup_hash(
        "BBVA", date(2024, 6, 1), Decimal("-42.50"), "MERCADONA"
    )

    fake_run = MagicMock(id=1, account_id=1)
    category_mock = MagicMock(id=5)

    async def _run_one(tx_to_insert: ExtractedTransaction, inserted_id: int | None):
        captured: dict = {}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = inserted_id
        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        def fake_pg_insert(table):
            stmt = MagicMock()

            def capture(**kw):
                captured.update(kw)
                return stmt

            stmt.values = MagicMock(side_effect=capture)
            stmt.on_conflict_do_nothing = MagicMock(return_value=stmt)
            stmt.returning = MagicMock(return_value=stmt)
            return stmt

        with patch(
            "finlytics.db.repository.get_or_create_category",
            new_callable=AsyncMock,
            return_value=category_mock,
        ):
            with patch("finlytics.db.repository.pg_insert", side_effect=fake_pg_insert):
                with patch(
                    "finlytics.db.repository.uuid.uuid4",
                    return_value=SimpleNamespace(hex="forceduplicate1"),
                ):
                    counts = await upsert_transactions(session, fake_run, [tx_to_insert])
        return counts, captured

    default_counts, default_values = await _run_one(tx, inserted_id=None)
    forced_counts, forced_values = await _run_one(forced_tx, inserted_id=101)

    assert default_counts == (0, 1)
    assert default_values["dedup_hash"] == natural_hash
    assert forced_counts == (1, 0)
    assert forced_values["dedup_hash"] != natural_hash
    assert len(forced_values["dedup_hash"]) == 64


async def test_upsert_two_identical_transactions_second_forced_both_inserted():
    """An intra-batch repeat inserts when the repeated row has allow_duplicate=True."""
    tx = ExtractedTransaction(
        transaction_date=date(2024, 6, 1),
        amount=Decimal("-42.50"),
        currency="EUR",
        description="MERCADONA",
        category="Groceries",
        account_ref="BBVA",
    )
    forced_tx = tx.model_copy(update={"allow_duplicate": True})

    fake_run = MagicMock(id=1, account_id=1)
    category_mock = MagicMock(id=5)
    session = AsyncMock()
    result_1 = MagicMock()
    result_1.scalar_one_or_none.return_value = 1
    result_2 = MagicMock()
    result_2.scalar_one_or_none.return_value = 2
    session.execute = AsyncMock(side_effect=[result_1, result_2])
    captured_hashes: list[str] = []

    def fake_pg_insert(table):
        stmt = MagicMock()

        def capture(**kw):
            captured_hashes.append(kw["dedup_hash"])
            return stmt

        stmt.values = MagicMock(side_effect=capture)
        stmt.on_conflict_do_nothing = MagicMock(return_value=stmt)
        stmt.returning = MagicMock(return_value=stmt)
        return stmt

    with patch(
        "finlytics.db.repository.get_or_create_category",
        new_callable=AsyncMock,
        return_value=category_mock,
    ):
        with patch("finlytics.db.repository.pg_insert", side_effect=fake_pg_insert):
            with patch(
                "finlytics.db.repository.uuid.uuid4",
                return_value=SimpleNamespace(hex="forceduplicate2"),
            ):
                counts = await upsert_transactions(session, fake_run, [tx, forced_tx])

    assert counts == (2, 0)
    assert len(captured_hashes) == 2
    assert captured_hashes[0] != captured_hashes[1]
