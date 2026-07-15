"""Unit tests for FidelityESPPProvider and helpers.

Coverage
────────
* _compute_dedup_hash — determinism, sensitivity to every input field.
* FidelityESPPProvider.import_lots — file-level idempotency (file_hash),
  lot-level idempotency (dedup_hash conflict → skipped), audit-trail recording,
  empty-lot edge case, identical-DO-lot ordinal separation.
* compute_evolution_series — edge cases that complement Shuri's 29 tests in
  test_market_data.py (boundary granularity, step-function correctness,
  no-price gap, identical DO lots cost accumulation).

No network, no DB (async session fully mocked).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from finlytics.api.fidelity import compute_evolution_series
from finlytics.api.schemas import ValuePoint
from finlytics.investments.fidelity import FidelityESPPProvider, _compute_dedup_hash


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@dataclass
class _Lot:
    """Minimal duck-type satisfying FidelityESPPProvider.import_lots protocol."""

    purchase_date: date
    shares: Decimal
    cost_basis: Decimal
    cost_basis_per_share: Decimal
    source_currency: str
    share_source: str
    grant_date: date | None
    holding_period: str | None
    dedup_ordinal: int


def _make_session() -> MagicMock:
    """Async session mock: supports async with db.begin() + execute + add."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)
    return session


def _exec_result(scalar=None) -> MagicMock:
    """Return a mock DB result whose scalar_one_or_none() returns *scalar*."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    return r


def _sp_lot(
    purchase_date: date = date(2024, 6, 30),
    shares: Decimal = Decimal("100.0000"),
    cbps: Decimal = Decimal("40.000000"),
    ordinal: int = 0,
) -> _Lot:
    return _Lot(
        purchase_date=purchase_date,
        shares=shares,
        cost_basis=shares * cbps,
        cost_basis_per_share=cbps,
        source_currency="EUR",
        share_source="SP",
        grant_date=date(2024, 4, 1),
        holding_period="Long",
        dedup_ordinal=ordinal,
    )


# ===========================================================================
# _compute_dedup_hash
# ===========================================================================

class TestComputeDedupHash:
    """Pure-function tests — no mocking needed."""

    _BASE = dict(
        ticker="MSFT",
        purchase_date=date(2024, 6, 30),
        shares=Decimal("100.00000000"),
        cost_basis_per_share=Decimal("40.000000"),
        share_source="SP",
        dedup_ordinal=0,
    )

    def test_deterministic_same_hash_on_same_inputs(self):
        h1 = _compute_dedup_hash(**self._BASE)
        h2 = _compute_dedup_hash(**self._BASE)
        assert h1 == h2

    def test_returns_64_char_lowercase_hex(self):
        h = _compute_dedup_hash(**self._BASE)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_purchase_date_produces_different_hash(self):
        h1 = _compute_dedup_hash(**self._BASE)
        h2 = _compute_dedup_hash(**{**self._BASE, "purchase_date": date(2025, 1, 1)})
        assert h1 != h2

    def test_different_ordinal_produces_different_hash(self):
        """Identical DO lots (same date/qty/price) get distinct hashes via ordinal."""
        h0 = _compute_dedup_hash(**{**self._BASE, "dedup_ordinal": 0})
        h1 = _compute_dedup_hash(**{**self._BASE, "dedup_ordinal": 1})
        assert h0 != h1

    def test_different_share_source_produces_different_hash(self):
        h_sp = _compute_dedup_hash(**self._BASE)
        h_do = _compute_dedup_hash(**{**self._BASE, "share_source": "DO"})
        assert h_sp != h_do

    def test_different_shares_produces_different_hash(self):
        h1 = _compute_dedup_hash(**self._BASE)
        h2 = _compute_dedup_hash(**{**self._BASE, "shares": Decimal("50.00000000")})
        assert h1 != h2

    def test_identical_do_lots_via_parser_dataclass(self):
        """Simulate the ordinal-0/1 scenario that comes from Banner's parser."""
        h_ord0 = _compute_dedup_hash(
            ticker="MSFT",
            purchase_date=date(2024, 12, 15),
            shares=Decimal("0.55000000"),
            cost_basis_per_share=Decimal("40.000000"),
            share_source="DO",
            dedup_ordinal=0,
        )
        h_ord1 = _compute_dedup_hash(
            ticker="MSFT",
            purchase_date=date(2024, 12, 15),
            shares=Decimal("0.55000000"),
            cost_basis_per_share=Decimal("40.000000"),
            share_source="DO",
            dedup_ordinal=1,
        )
        assert h_ord0 != h_ord1


# ===========================================================================
# FidelityESPPProvider.import_lots — file-level idempotency
# ===========================================================================

class TestImportLotsFileDedup:
    """file_hash already in investment_import_runs → return previous counts immediately."""

    @pytest.fixture
    def provider(self) -> FidelityESPPProvider:
        return FidelityESPPProvider()

    async def test_returns_previous_counts_when_file_already_imported(self, provider):
        session = _make_session()
        existing_run = MagicMock(lots_inserted=3, lots_skipped=2)
        session.execute.return_value = _exec_result(scalar=existing_run)

        inserted, skipped = await provider.import_lots(
            connection_id=1, lots=[], source_currency="EUR",
            file_hash="existing_hash", db=session,
        )

        assert inserted == 3
        assert skipped == 2

    async def test_only_one_execute_call_when_file_already_imported(self, provider):
        """No lot inserts or import-run creation — just the file-check query."""
        session = _make_session()
        existing_run = MagicMock(lots_inserted=3, lots_skipped=0)
        session.execute.return_value = _exec_result(scalar=existing_run)

        await provider.import_lots(
            connection_id=1, lots=[_sp_lot()], source_currency="EUR",
            file_hash="existing_hash", db=session,
        )

        assert session.execute.await_count == 1

    async def test_no_import_run_added_when_file_already_imported(self, provider):
        session = _make_session()
        existing_run = MagicMock(lots_inserted=3, lots_skipped=0)
        session.execute.return_value = _exec_result(scalar=existing_run)

        await provider.import_lots(
            connection_id=1, lots=[_sp_lot()], source_currency="EUR",
            file_hash="existing_hash", db=session,
        )

        session.add.assert_not_called()


# ===========================================================================
# FidelityESPPProvider.import_lots — lot-level idempotency
# ===========================================================================

class TestImportLotsLotDedup:
    """INSERT ON CONFLICT DO NOTHING: None from RETURNING → skipped, not None → inserted."""

    @pytest.fixture
    def provider(self) -> FidelityESPPProvider:
        return FidelityESPPProvider()

    async def test_all_new_lots_are_inserted(self, provider):
        session = _make_session()
        no_run = _exec_result(scalar=None)                      # no existing import run
        inserted_row = _exec_result(scalar=MagicMock(id=1))     # RETURNING row present

        lots = [_sp_lot(date(2024, 6, 30)), _sp_lot(date(2025, 3, 31))]
        session.execute = AsyncMock(side_effect=[no_run, inserted_row, inserted_row])

        ins, skipped = await provider.import_lots(
            connection_id=1, lots=lots, source_currency="EUR",
            file_hash="new_file", db=session,
        )

        assert ins == 2
        assert skipped == 0

    async def test_conflict_on_one_lot_increments_skipped(self, provider):
        """First lot: ON CONFLICT DO NOTHING (None); second lot: inserted."""
        session = _make_session()
        no_run = _exec_result(scalar=None)
        conflict = _exec_result(scalar=None)         # None → conflict → skipped
        inserted = _exec_result(scalar=MagicMock(id=2))

        lots = [_sp_lot(date(2024, 6, 30)), _sp_lot(date(2025, 3, 31))]
        session.execute = AsyncMock(side_effect=[no_run, conflict, inserted])

        ins, skipped = await provider.import_lots(
            connection_id=1, lots=lots, source_currency="EUR",
            file_hash="partial_reimport", db=session,
        )

        assert ins == 1
        assert skipped == 1

    async def test_all_lots_conflict_all_skipped(self, provider):
        session = _make_session()
        no_run = _exec_result(scalar=None)
        conflict = _exec_result(scalar=None)

        lots = [_sp_lot(date(2024, 6, 30)), _sp_lot(date(2025, 3, 31))]
        session.execute = AsyncMock(side_effect=[no_run, conflict, conflict])

        ins, skipped = await provider.import_lots(
            connection_id=1, lots=lots, source_currency="EUR",
            file_hash="full_reimport", db=session,
        )

        assert ins == 0
        assert skipped == 2

    async def test_empty_lots_returns_zero_zero(self, provider):
        session = _make_session()
        session.execute.return_value = _exec_result(scalar=None)  # no existing run

        ins, skipped = await provider.import_lots(
            connection_id=1, lots=[], source_currency="EUR",
            file_hash="empty_file", db=session,
        )

        assert ins == 0
        assert skipped == 0


# ===========================================================================
# FidelityESPPProvider.import_lots — audit trail
# ===========================================================================

class TestImportLotsAuditTrail:
    """InvestmentImportRun must be db.add()ed for every new file."""

    @pytest.fixture
    def provider(self) -> FidelityESPPProvider:
        return FidelityESPPProvider()

    async def test_import_run_added_for_new_file_with_lots(self, provider):
        session = _make_session()
        session.execute = AsyncMock(side_effect=[
            _exec_result(scalar=None),                   # no existing run
            _exec_result(scalar=MagicMock(id=1)),        # lot inserted
        ])

        await provider.import_lots(
            connection_id=1, lots=[_sp_lot()], source_currency="EUR",
            file_hash="new_file", db=session,
        )

        session.add.assert_called_once()

    async def test_import_run_added_even_for_empty_lots_list(self, provider):
        """Even a file with zero parseable lots records a run."""
        session = _make_session()
        session.execute.return_value = _exec_result(scalar=None)

        await provider.import_lots(
            connection_id=1, lots=[], source_currency="EUR",
            file_hash="zero_lots_file", db=session,
        )

        session.add.assert_called_once()

    async def test_import_run_not_added_when_file_is_duplicate(self, provider):
        session = _make_session()
        existing_run = MagicMock(lots_inserted=1, lots_skipped=0)
        session.execute.return_value = _exec_result(scalar=existing_run)

        await provider.import_lots(
            connection_id=1, lots=[_sp_lot()], source_currency="EUR",
            file_hash="dup_file", db=session,
        )

        session.add.assert_not_called()


# ===========================================================================
# compute_evolution_series — edge cases beyond Shuri's 29 tests
# ===========================================================================

@dataclass
class _LotForEvol:
    purchase_date: date
    shares: Decimal
    cost_basis: Decimal


class TestComputeEvolutionSeriesEdgeCases:
    """Gaps in test_market_data.py coverage — pure function, no mocking."""

    # -- granularity boundary ------------------------------------------------

    def test_366_day_range_now_daily_market_day(self):
        """total_days = 366 ≤ 2200 → daily market-day (not weekly).  2024 is a leap year so Jul1→Jul2 = 366 days."""
        lot = _LotForEvol(date(2024, 7, 1), Decimal("10"), Decimal("500.00"))
        pm = {date(2024, 7, 1): (400.0, 0.926)}
        min_d, max_d = date(2024, 7, 1), date(2025, 7, 2)
        assert (max_d - min_d).days == 366
        _, cs = compute_evolution_series([lot], pm, min_d, max_d)
        # daily market-day → 1 point (only 1 trading day in price_map within range)
        assert len(cs) == 1

    def test_365_day_range_stays_daily_market_day(self):
        """total_days = 365 ≤ 2200 → daily market-day resolution."""
        lot = _LotForEvol(date(2025, 7, 15), Decimal("10"), Decimal("500.00"))
        pm = {date(2025, 7, 15): (450.0, 0.926)}
        min_d = date(2025, 7, 15)
        max_d = date(2026, 7, 15)   # exactly 365 days (no leap year in 2026)
        assert (max_d - min_d).days == 365
        _, cs = compute_evolution_series([lot], pm, min_d, max_d)
        # 1 market day in price_map → 1 point
        assert len(cs) == 1

    # -- step function -------------------------------------------------------

    def test_contributions_include_lot_on_its_purchase_date(self):
        """cost_basis accumulates on purchase_date itself (≤ sd)."""
        lot = _LotForEvol(date(2026, 6, 30), Decimal("50"), Decimal("2000.00"))
        pm = {date(2026, 6, 30): (400.0, 0.926)}
        _, cs = compute_evolution_series([lot], pm, date(2026, 6, 30), date(2026, 6, 30))
        assert len(cs) == 1
        assert cs[0].value == pytest.approx(2000.0, abs=0.01)
        assert cs[0].date == "2026-06-30"

    def test_no_value_point_before_first_price_in_map(self):
        """Days with no price and no forward-fill → no value point emitted."""
        lot = _LotForEvol(date(2026, 6, 28), Decimal("10"), Decimal("400.00"))
        pm = {date(2026, 6, 30): (400.0, 0.926)}  # price only from Jun-30
        vs, _ = compute_evolution_series([lot], pm, date(2026, 6, 28), date(2026, 6, 30))
        dates = {pt.date for pt in vs}
        assert "2026-06-28" not in dates
        assert "2026-06-29" not in dates
        assert "2026-06-30" in dates

    def test_two_identical_do_lots_both_contribute_to_cost(self):
        """Both DO lots (ordinals 0 and 1) with same date add to cum_cost."""
        lot_a = _LotForEvol(date(2024, 12, 15), Decimal("0.55"), Decimal("22.00"))
        lot_b = _LotForEvol(date(2024, 12, 15), Decimal("0.55"), Decimal("22.00"))
        pm = {date(2024, 12, 15): (400.0, 0.926)}
        _, cs = compute_evolution_series([lot_a, lot_b], pm, date(2024, 12, 15), date(2024, 12, 15))
        assert len(cs) == 1
        assert cs[0].value == pytest.approx(44.0, abs=0.01)   # 22 + 22

    def test_value_point_uses_isoformat_date_string(self):
        """ValuePoint.date is 'YYYY-MM-DD', not a date object."""
        lot = _LotForEvol(date(2026, 6, 30), Decimal("50"), Decimal("2000.00"))
        pm = {date(2026, 6, 30): (400.0, 0.926)}
        vs, _ = compute_evolution_series([lot], pm, date(2026, 6, 30), date(2026, 6, 30))
        assert len(vs) == 1
        assert isinstance(vs[0].date, str)
        assert vs[0].date == "2026-06-30"
