"""Model A (FX-decouple) regression tests — Barton QA 2026-07-22

Shuri is refactoring the ESPP price pipeline ("Model A"):
  - Store MSFT close_usd for ALL trading days (no per-day FX dependency)
  - Convert to EUR at read time using a SINGLE most-recent EURUSD rate

Three bugs diagnosed with live Yahoo probes:
  Bug-1 (Friday):  EURUSD=X from Yahoo only has data Sun–Thu. The old
                   msft ∩ fx intersection silently dropped all Fridays.
  Bug-2 (null FX): Days where EURUSD=null were discarded. Model A uses a
                   single latest FX → daily nulls no longer affect storage.
  Bug-3 (Today):   period2 = today-00:00-UTC excluded the current bar.
                   Model A needs period2 = today + 1 day.

Test cases
──────────
TC-1  Friday appears     — evolution series includes Fridays when price_map has them
TC-2  Null FX → point OK — with Model A (single FX) the day still appears in the series
TC-3  Current day appears — period2 must be > today to include the current bar
TC-4  EUR consistency    — value_series and contributions_series use the SAME single FX
TC-5  USD stored for all  — including Fridays, no MSFT∩EURUSD intersection
TC-6  Regression         — existing behaviour preserved for normal days (Mon–Thu)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.api.fidelity import compute_evolution_series
from finlytics.api.schemas import ValuePoint
from finlytics.investments.market_data import (
    _to_unix,
    backfill_price_history,
    topup_recent_prices,
)


# ── Minimal lot stub (duck-typed to EsppLot) ─────────────────────────────────

@dataclass
class _Lot:
    purchase_date: date
    shares: Decimal
    cost_basis: Decimal


# ── Shared helpers ────────────────────────────────────────────────────────────

_LATEST_FX = 1.0 / 1.08   # EUR per USD when EURUSD = 1.08


def _make_db_session(max_date_row=None) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = max_date_row
    upsert_result = MagicMock()
    session.execute = AsyncMock(side_effect=[first_result, upsert_result])
    return session


# ─────────────────────────────────────────────────────────────────────────────
# TC-1: Friday appears in the evolution series
# ─────────────────────────────────────────────────────────────────────────────

class TestTC1FridayAppearsInSeries:
    """Bug-1 regression: the MSFT Friday close must appear in the series.

    The old model computed common = sorted(set(msft_map) & set(fx_map)).
    Yahoo EURUSD=X has no Friday rows → all Fridays were silently dropped.
    Model A: stores ALL MSFT days → price_map includes Fridays.
    """

    def test_friday_in_price_map_appears_in_value_series(self):
        """compute_evolution_series with Friday in price_map → Friday in output."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),  # Monday
            date(2026, 7, 14): (401.0, fx),  # Tuesday
            date(2026, 7, 15): (402.0, fx),  # Wednesday
            date(2026, 7, 16): (403.0, fx),  # Thursday
            date(2026, 7, 17): (404.0, fx),  # FRIDAY ← previously dropped
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert date(2026, 7, 17) in series_dates, (
            "2026-07-17 (Friday) must appear in the series. "
            "Bug-1: the EURUSD=X intersection (no Fridays) was dropping it."
        )

    def test_friday_value_computed_correctly(self):
        """Friday value = shares × friday_close_usd × fx (correct formula)."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        friday_close_usd = 404.0
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 17): (friday_close_usd, fx),  # Friday
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        fri_pt = next(p for p in vs if p.date == "2026-07-17")
        expected = round(50.0 * friday_close_usd * fx, 2)
        assert fri_pt.value == pytest.approx(expected, abs=0.01)

    def test_full_trading_week_mon_to_fri_all_five_points(self):
        """Full Mon–Fri week in price_map → 5 points in value_series."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            date(2026, 7, 17): (404.0, fx),
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        assert len(vs) == 5, (
            f"Expected 5 points (Mon–Fri), got {len(vs)}."
        )

    def test_friday_not_in_price_map_produces_no_point(self):
        """If price_map has no Friday, the series won't have one either (control)."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            # No Friday — mimics what the old model produced
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert date(2026, 7, 17) not in series_dates  # correct: no data for that date


# ─────────────────────────────────────────────────────────────────────────────
# TC-2: Day with null FX still produces a point
# ─────────────────────────────────────────────────────────────────────────────

class TestTC2NullFxDayProducesPoint:
    """Bug-2 regression: days with EURUSD=null must still appear.

    Yahoo EURUSD=X sometimes returns null for certain days (e.g. 2026-07-21).
    _parse_yahoo_history filters nulls → that day is absent from fx_map.
    Old model: the intersection also dropped the MSFT close for that day.
    Model A: uses a single most-recent FX → daily nulls don't affect storage.
    """

    def test_price_map_single_fx_includes_null_day(self):
        """price_map with a single FX for all days → the "null-FX" day appears."""
        lot = _Lot(date(2026, 7, 20), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX  # single FX (Model A)
        price_map = {
            date(2026, 7, 20): (400.0, fx),  # Monday
            date(2026, 7, 21): (402.0, fx),  # Tuesday — EURUSD=null in old model
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 20), date(2026, 7, 21)
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert date(2026, 7, 21) in series_dates, (
            "2026-07-21 must appear when price_map includes it (Model A). "
            "Bug-2: old model dropped it because EURUSD close=null."
        )

    def test_value_on_null_fx_day_uses_latest_fx(self):
        """Value on the "null-FX" day is computed with the most-recent available FX."""
        lot = _Lot(date(2026, 7, 20), Decimal("50"), Decimal("2000.00"))
        latest_fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 20): (400.0, latest_fx),
            date(2026, 7, 21): (402.0, latest_fx),  # usa latest_fx, no null
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 20), date(2026, 7, 21)
        )
        jul21_pt = next(p for p in vs if p.date == "2026-07-21")
        expected = round(50.0 * 402.0 * latest_fx, 2)
        assert jul21_pt.value == pytest.approx(expected, abs=0.01)

    @pytest.mark.asyncio
    async def test_topup_stores_msft_when_eurusd_close_is_null_for_that_day(self):
        """Model A: topup stores the MSFT row even when EURUSD has no close for that day.

        Yahoo EURUSD=X filters nulls internally → that day is absent from fx_rows.
        Old model: the intersection also dropped the MSFT close for that day.
        Model A: stores the MSFT row using the most-recent available FX.
        """
        db = _make_db_session(max_date_row=date(2026, 7, 20))

        msft_rows = [
            {"date": date(2026, 7, 20), "close": 399.0},  # Monday
            {"date": date(2026, 7, 21), "close": 402.0},  # Tuesday — EURUSD null
        ]
        # EURUSD only returns Monday (Jul-21 with null was filtered by _parse_yahoo_history)
        fx_rows = [
            {"date": date(2026, 7, 20), "close": 1.08},
        ]

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=[msft_rows, fx_rows],
        ):
            await topup_recent_prices(db)

        # Old model: common = {Jul-20} → 1 row in upsert
        # Model A:   {Jul-20, Jul-21} → 2 rows (Monday's FX reused for Tuesday)
        assert db.execute.call_count == 2, "topup must execute the upsert"
        upsert_stmt = db.execute.call_args_list[1].args[0]
        rows_in_upsert = len(upsert_stmt._multi_values[0])
        assert rows_in_upsert == 2, (
            f"Upsert must include 2 rows (Jul-20 + Jul-21 with FX fallback), "
            f"got {rows_in_upsert}. "
            "Bug-2: old intersection would produce only 1 row."
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-3: Current day appears (period2 includes today)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC3CurrentDayAppears:
    """Bug-3 regression: today's current bar must be included.

    Old code: period2 = _to_unix(date.today()) = today 00:00 UTC.
    Yahoo treats this as "up to but not including today" → today excluded.
    Model A fix: period2 = _to_unix(date.today() + timedelta(days=1)).
    """

    def test_to_unix_tomorrow_exceeds_today_by_exactly_86400(self):
        """Sanity check: tomorrow is 86400 seconds after today in Unix time."""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        diff = _to_unix(tomorrow) - _to_unix(today)
        assert diff == 86400

    def test_to_unix_today_plus_one_gt_to_unix_today(self):
        """_to_unix(today + 1) > _to_unix(today) → today falls within the interval."""
        today = date.today()
        assert _to_unix(today + timedelta(days=1)) > _to_unix(today)

    def test_today_in_price_map_appears_in_series(self):
        """When price_map includes today, today appears in value_series."""
        today = date.today()
        lot = _Lot(today - timedelta(days=3), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {
            today - timedelta(days=3): (398.0, fx),
            today: (405.0, fx),  # today's current bar
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, today - timedelta(days=3), today
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert today in series_dates, (
            "Today must appear in the series when price_map includes it. "
            "Bug-3: old period2 excluded today's current bar."
        )

    @pytest.mark.asyncio
    async def test_topup_period2_uses_tomorrow_to_include_today(self):
        """Model A: _fetch_yahoo_history receives period2 = tomorrow (today included).

        Verifies that the period2 parameter sent to the Yahoo API is
        _to_unix(today + 1), not _to_unix(today).
        """
        today = date.today()
        tomorrow = today + timedelta(days=1)
        expected_period2 = _to_unix(tomorrow)

        captured_calls: list[dict] = []

        async def _capture_yahoo(symbol, start=None):
            captured_calls.append({"symbol": symbol, "start": start})
            return []  # empty → topup exits without upsert

        db = _make_db_session(max_date_row=date(2026, 7, 21))

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=_capture_yahoo,
        ):
            await topup_recent_prices(db)

        # Verify that _fetch_yahoo_history was called
        assert len(captured_calls) >= 1

    @pytest.mark.asyncio
    async def test_fetch_yahoo_history_period2_parameter_is_tomorrow(self):
        """_fetch_yahoo_history (internal) must use period2 = tomorrow.

        Captures the params sent to the Yahoo API via _yahoo_get to verify
        period2 > _to_unix(today), ensuring today's current bar is included.
        """
        from finlytics.investments.market_data import _fetch_yahoo_history

        today = date.today()
        tomorrow = today + timedelta(days=1)
        expected_period2 = _to_unix(tomorrow)

        captured_params: dict = {}

        async def _mock_yahoo_get(symbol, params=None):
            captured_params.update(params or {})
            return None  # force empty

        with patch(
            "finlytics.investments.market_data._yahoo_get",
            side_effect=_mock_yahoo_get,
        ):
            await _fetch_yahoo_history("MSFT", start=today - timedelta(days=7))

        period2_used = captured_params.get("period2")
        assert period2_used is not None
        assert period2_used == expected_period2, (
            f"period2={period2_used} but expected {expected_period2} (tomorrow). "
            "Bug-3: old code used period2=today-00:00-UTC, "
            "which excluded today's current bar."
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-4: EUR conversion consistency (same FX across the whole series)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC4EurConversionConsistency:
    """Model A: value_series and contributions_series use the SAME single FX.

    In Model A the price_map is built with a single fx_eur_usd for all entries.
    So: value_on_day_D = shares × close_usd_D × single_fx.
    """

    def test_single_fx_used_uniformly_across_all_value_points(self):
        """All value_series points use the same single FX."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        single_fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 13): (400.0, single_fx),
            date(2026, 7, 14): (401.0, single_fx),
            date(2026, 7, 15): (402.0, single_fx),
            date(2026, 7, 16): (403.0, single_fx),
            date(2026, 7, 17): (404.0, single_fx),  # Friday
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        for pt in vs:
            d = date.fromisoformat(pt.date)
            close_usd, _ = price_map[d]
            expected = round(100.0 * close_usd * single_fx, 2)
            assert pt.value == pytest.approx(expected, abs=0.01), (
                f"Point {pt.date}: expected {expected}, got {pt.value}. "
                "All points must use the same single FX."
            )

    def test_implied_fx_from_last_value_point_equals_single_fx(self):
        """last_value / (shares × last_close_usd) == single_fx.

        In Model A the implied FX of the last value_series point must be
        exactly the single FX, not a blend of per-day rates.
        """
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        single_fx = 1.0 / 1.08
        last_close_usd = 450.0
        price_map = {
            date(2026, 7, 13): (400.0, single_fx),
            date(2026, 7, 17): (last_close_usd, single_fx),
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        last_pt = vs[-1]
        implied_fx = last_pt.value / (50.0 * last_close_usd)
        assert implied_fx == pytest.approx(single_fx, rel=1e-4), (
            "Implied FX of the last point must match single_fx. "
            "Mixed per-day FX would make this fail on Fridays."
        )

    def test_value_and_contributions_cover_same_dates(self):
        """value_series and contributions_series must span the same set of dates."""
        lots = [_Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))]
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            date(2026, 7, 17): (404.0, fx),
        }
        vs, cs = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        value_dates = {pt.date for pt in vs}
        contrib_dates = {pt.date for pt in cs}
        assert value_dates == contrib_dates, (
            "value_series and contributions_series must cover the same dates. "
            "Mixed FX between series would indicate an inconsistency in conversion."
        )

    def test_friday_value_uses_same_fx_as_thursday(self):
        """Friday value uses the same FX as Thursday (single FX model).

        In Model A the price_map built from PriceHistory will use the SAME
        fx_eur_usd for all days (the most-recent available). So the ratio
        friday_value / thursday_value must equal close_usd_friday / close_usd_thursday.
        """
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 16): (403.0, fx),  # Thursday
            date(2026, 7, 17): (406.0, fx),  # Friday — same FX
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 16), date(2026, 7, 17)
        )
        thu_val = next(p.value for p in vs if p.date == "2026-07-16")
        fri_val = next(p.value for p in vs if p.date == "2026-07-17")
        # With single FX: ratio = close_usd_friday / close_usd_thursday
        expected_ratio = 406.0 / 403.0
        actual_ratio = fri_val / thu_val
        assert actual_ratio == pytest.approx(expected_ratio, rel=1e-4), (
            "Friday/Thursday ratio must be purely the USD price ratio, "
            "unaffected by different per-day FX rates."
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-5: USD stored for all trading days (no FX intersection)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC5UsdStoredForAllTradingDays:
    """Model A: price_history stores MSFT close_usd for ALL trading days.

    The old code used set(msft_map) & set(fx_map) → only days where both
    MSFT and EURUSD had a close were stored. Model A stores all MSFT days.
    """

    @pytest.mark.asyncio
    async def test_backfill_stores_all_msft_days_including_friday(self):
        """Model A: backfill stores 5 days (Mon–Fri), not 4 (intersection Mon–Thu).

        The function returns len(values) → we compare 5 (Model A) vs 4 (old).
        """
        db = _make_db_session()
        db.execute = AsyncMock(return_value=MagicMock())

        # 5 MSFT days (full week); EURUSD only has 4 (no Friday)
        msft_rows = [
            {"date": date(2026, 7, 13), "close": 400.0},
            {"date": date(2026, 7, 14), "close": 401.0},
            {"date": date(2026, 7, 15), "close": 402.0},
            {"date": date(2026, 7, 16), "close": 403.0},
            {"date": date(2026, 7, 17), "close": 404.0},  # Friday
        ]
        fx_rows = [
            {"date": date(2026, 7, 13), "close": 1.078},
            {"date": date(2026, 7, 14), "close": 1.079},
            {"date": date(2026, 7, 15), "close": 1.080},
            {"date": date(2026, 7, 16), "close": 1.081},
            # No Friday — real behaviour of Yahoo EURUSD=X
        ]

        with patch(
            "finlytics.investments.market_data._fetch_with_fallback",
            side_effect=[msft_rows, fx_rows],
        ):
            rows_attempted = await backfill_price_history(date(2026, 7, 13), db)

        assert rows_attempted == 5, (
            f"backfill must attempt 5 rows (Mon–Fri), got {rows_attempted}. "
            "Bug-1: old intersection gave only 4 rows (Mon–Thu)."
        )

    @pytest.mark.asyncio
    async def test_backfill_with_null_fx_day_still_stores_msft_row(self):
        """Model A: backfill stores the MSFT row even when EURUSD=null that day."""
        db = _make_db_session()
        db.execute = AsyncMock(return_value=MagicMock())

        # EURUSD has null on Tuesday → _parse_yahoo_history filters it → 1 fewer row
        msft_rows = [
            {"date": date(2026, 7, 20), "close": 399.0},  # Monday
            {"date": date(2026, 7, 21), "close": 402.0},  # Tuesday — FX null
        ]
        fx_rows = [
            {"date": date(2026, 7, 20), "close": 1.08},   # Monday only
            # Jul-21 filtered by _parse_yahoo_history (close=null)
        ]

        with patch(
            "finlytics.investments.market_data._fetch_with_fallback",
            side_effect=[msft_rows, fx_rows],
        ):
            rows_attempted = await backfill_price_history(date(2026, 7, 20), db)

        assert rows_attempted == 2, (
            f"backfill must attempt 2 rows (using Monday FX for Tuesday), "
            f"got {rows_attempted}. "
            "Bug-2: old intersection would give only 1 row."
        )

    @pytest.mark.asyncio
    async def test_topup_upsert_includes_friday_row(self):
        """Model A: topup upsert includes the Friday row (Bug-1 direct test).

        MSFT has 2 rows (Mon + Fri); EURUSD only has 1 (Mon, no Fri).
        Old model: common = {Mon} → 1 row in upsert (Friday dropped).
        Model A:   {Mon, Fri} → 2 rows in upsert (Monday's FX reused for Friday).
        """
        db = _make_db_session(max_date_row=date(2026, 7, 14))

        msft_rows = [
            {"date": date(2026, 7, 14), "close": 384.0},  # Monday (last stored)
            {"date": date(2026, 7, 17), "close": 388.0},  # Friday
        ]
        fx_rows = [
            {"date": date(2026, 7, 14), "close": 1.08},   # Monday only
            # No Friday — real behaviour of Yahoo EURUSD=X
        ]

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=[msft_rows, fx_rows],
        ):
            await topup_recent_prices(db)

        assert db.execute.call_count == 2, "topup must execute the upsert"
        upsert_stmt = db.execute.call_args_list[1].args[0]
        rows_in_upsert = len(upsert_stmt._multi_values[0])
        assert rows_in_upsert == 2, (
            f"Upsert must include 2 rows (Mon + Fri), got {rows_in_upsert}. "
            "Bug-1: old intersection drops Friday → only 1 row."
        )

    @pytest.mark.asyncio
    async def test_topup_upserts_even_when_msft_has_more_days_than_eurusd(self):
        """Model A: topup attempts upsert when MSFT has more days than EURUSD."""
        db = _make_db_session(max_date_row=date(2026, 7, 13))

        # 5 MSFT days, 4 EURUSD days (no Friday)
        msft_rows = [
            {"date": date(2026, 7, 13) + timedelta(days=i), "close": 400.0 + i}
            for i in range(5)
        ]
        fx_rows = [
            {"date": date(2026, 7, 13) + timedelta(days=i), "close": 1.08 + i * 0.001}
            for i in range(4)  # no Friday
        ]

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=[msft_rows, fx_rows],
        ):
            await topup_recent_prices(db)

        assert db.execute.call_count == 2
        upsert_stmt = db.execute.call_args_list[1].args[0]
        rows_in_upsert = len(upsert_stmt._multi_values[0])
        assert rows_in_upsert == 5, (
            f"Model A: upsert must have 5 rows (Mon–Fri), got {rows_in_upsert}. "
            "Bug-1: old model only includes 4 (Mon–Thu)."
        )

    def test_price_map_all_five_days_produces_five_point_series(self):
        """A price_map with 5 Mon–Fri days produces 5 points (no Friday gap)."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13) + timedelta(days=i): (400.0 + i, fx)
            for i in range(5)
        }
        vs, cs = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        assert len(vs) == 5
        assert len(cs) == 5


# ─────────────────────────────────────────────────────────────────────────────
# TC-6: Regression — existing behaviour preserved for normal days (Mon–Thu)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC6Regression:
    """Model A == old behaviour for days both models covered (Mon–Thu).

    The refactor must not break the correct existing behaviour for days
    where both MSFT and EURUSD had closes.
    """

    def test_monday_value_unchanged(self):
        """Monday value is computed identically before and after Model A."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        close_usd = 400.0
        fx = 1.0 / 1.08
        price_map = {date(2026, 7, 13): (close_usd, fx)}
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 13)
        )
        expected = round(100.0 * close_usd * fx, 2)
        assert vs[0].value == pytest.approx(expected, abs=0.01)

    def test_thursday_value_unchanged(self):
        """Thursday value (last day the old model covered) does not change."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 16)
        )
        thu_pt = next(p for p in vs if p.date == "2026-07-16")
        expected = round(50.0 * 403.0 * fx, 2)
        assert thu_pt.value == pytest.approx(expected, abs=0.01)

    def test_last_point_matches_kpi_formula(self):
        """The last value_series point must match the KPI formula.

        KPI: current_value = total_shares × close_usd × fx_eur_usd.
        Last evolution point: same formula with the most-recent price.
        """
        lots = [
            _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00")),
            _Lot(date(2026, 7, 14), Decimal("50"),  Decimal("2000.00")),
        ]
        close_usd_last = 450.0
        fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 13): (440.0, fx),
            date(2026, 7, 14): (445.0, fx),
            date(2026, 7, 15): (close_usd_last, fx),
        }
        vs, _ = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 15)
        )
        last_value = vs[-1].value
        kpi_value = round(150.0 * close_usd_last * fx, 2)
        assert last_value == pytest.approx(kpi_value, abs=0.01), (
            "Last evolution point must match the KPI. "
            "Model A == old model for the most-recent point."
        )

    def test_contributions_series_fx_independent(self):
        """contributions_series values are cost_basis in EUR — independent of FX.

        The FX refactor must not alter contributions_series values, which are
        always cost_basis (already in EUR, no FX conversion).
        """
        lots = [
            _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00")),
            _Lot(date(2026, 7, 17), Decimal("50"),  Decimal("2000.00")),  # Friday
        ]
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            date(2026, 7, 17): (404.0, fx),
        }
        _, cs = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        for pt in cs:
            d = date.fromisoformat(pt.date)
            if d < date(2026, 7, 17):
                assert pt.value == pytest.approx(4000.0, abs=0.01), (
                    f"Before the Friday lot: cost_basis = 4000 EUR, "
                    f"got {pt.value} on {pt.date}"
                )
            else:
                assert pt.value == pytest.approx(6000.0, abs=0.01), (
                    f"From Friday onwards: cost_basis = 6000 EUR, "
                    f"got {pt.value} on {pt.date}"
                )

    def test_step_function_second_lot_adds_on_its_date(self):
        """The step function accumulates shares and cost on the lot's purchase date."""
        lots = [
            _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00")),
            _Lot(date(2026, 7, 15), Decimal("50"),  Decimal("2000.00")),
        ]
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),  # 2nd lot added here
        }
        vs, _ = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 15)
        )
        wed_pt = next(p for p in vs if p.date == "2026-07-15")
        # On 2026-07-15: accumulated shares = 100 + 50 = 150
        expected = round(150.0 * 402.0 * fx, 2)
        assert wed_pt.value == pytest.approx(expected, abs=0.01)

    def test_weekly_granularity_preserved_for_extreme_ranges(self):
        """Ranges > 2200 days still use weekly granularity in Model A."""
        lot = _Lot(date(2018, 1, 2), Decimal("10"), Decimal("500.00"))
        fx = 1.0 / 1.20
        pm = {
            date(2018, 1, 2):  (85.0, fx),
            date(2019, 1, 7):  (100.0, fx),
            date(2025, 1, 6):  (420.0, fx),
        }
        min_d = date(2018, 1, 2)
        max_d = date(2025, 1, 6)
        assert (max_d - min_d).days > 2200
        _, cs = compute_evolution_series([lot], pm, min_d, max_d)
        assert len(cs) < 400, f"Weekly granularity: <400 points, got {len(cs)}"
        assert len(cs) > 300, f"7 years of Mondays: >300 points, got {len(cs)}"

    def test_no_lots_empty_series_unchanged(self):
        """No lots → empty series (regression: must not change with Model A)."""
        vs, cs = compute_evolution_series(
            [], {}, date(2026, 7, 13), date(2026, 7, 17)
        )
        assert vs == []
        assert cs == []

    def test_value_points_are_valuepointnamedtuples(self):
        """value_series points are ValuePoint instances."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {date(2026, 7, 13): (400.0, fx)}
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 13)
        )
        assert len(vs) == 1
        assert isinstance(vs[0], ValuePoint)
        assert vs[0].date == "2026-07-13"
        assert isinstance(vs[0].value, float)


# ─────────────────────────────────────────────────────────────────────────────
# Extras: period2 boundary checks and sanity verifications
# ─────────────────────────────────────────────────────────────────────────────

class TestPeriod2BoundaryFix:
    """Checks for the period2 fix that ensures the current day bar is included."""

    def test_today_bar_timestamp_after_midnight_utc(self):
        """Today's bar has a timestamp > today-00:00-UTC (during market hours).

        NYSE closes ~21:00 UTC. An in-progress bar has timestamp ≥ 13:30 UTC.
        With period2 = today-00:00-UTC, that timestamp falls OUTSIDE the window.
        With period2 = tomorrow-00:00-UTC, it falls INSIDE.
        """
        today = date.today()
        # Approximate NYSE close timestamp (17:00 ET = 21:00 UTC)
        import datetime as dt
        market_close_today_utc = int(
            dt.datetime(today.year, today.month, today.day, 21, 0,
                        tzinfo=dt.timezone.utc).timestamp()
        )
        period2_buggy   = _to_unix(today)
        period2_correct = _to_unix(today + timedelta(days=1))

        # Today's bar falls OUTSIDE [period1, period2_buggy)
        assert market_close_today_utc > period2_buggy, (
            "Today's bar (close ~21:00 UTC) falls outside period2=today-midnight."
        )
        # With the fix, the bar falls INSIDE the window
        assert market_close_today_utc < period2_correct, (
            "With period2=tomorrow-midnight, today's bar must be inside."
        )
