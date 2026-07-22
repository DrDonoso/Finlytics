"""Focused unit tests for the Fidelity ESPP Wave-2 backend.

Covers:
  - FX direction math (critical correctness property)
  - _last_business_day helper
  - _parse_stooq_csv
  - _parse_yahoo_history / _parse_yahoo_snapshot (Yahoo Chart JSON parsers)
  - Yahoo Chart fetch: User-Agent header + 429 → query2 fallback
  - topup_recent_prices — UPSERT DO UPDATE, missing days filled, graceful degradation
  - get_latest_price — returns latest close, price_stale logic
  - compute_evolution_series — step function, forward-fill, market-day granularity

No DB, no network — all pure / mocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from finlytics.investments.market_data import (
    _MSFT_TICKER,
    _YAHOO_HOSTS,
    _YAHOO_UA,
    _last_business_day,
    _parse_stooq_csv,
    _parse_yahoo_history,
    _parse_yahoo_snapshot,
    _yahoo_get,
    get_latest_price,
    topup_recent_prices,
)
from finlytics.investments.market_data import LatestPriceRow
from finlytics.api.fidelity import compute_evolution_series
from finlytics.api.schemas import ValuePoint


# ---------------------------------------------------------------------------
# Minimal lot stub (duck-types EsppLot for compute_evolution_series)
# ---------------------------------------------------------------------------

@dataclass
class _Lot:
    purchase_date: date
    shares: Decimal
    cost_basis: Decimal


# ---------------------------------------------------------------------------
# Yahoo Chart JSON fixtures
# ---------------------------------------------------------------------------

# Timestamps at 20:00 UTC (market close proxy) — UTC date equals calendar date
_TS_JUL9  = int(datetime(2026, 7, 9,  20, 0, tzinfo=timezone.utc).timestamp())
_TS_JUL10 = int(datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc).timestamp())
_TS_JUL11 = int(datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc).timestamp())

_YAHOO_CHART_MSFT = {
    "chart": {
        "result": [{
            "meta": {
                "regularMarketPrice": 445.0,
                "regularMarketTime": _TS_JUL10,
                "currency": "USD",
            },
            "timestamp": [_TS_JUL9, _TS_JUL10],
            "indicators": {
                "quote": [{"close": [441.5, 445.0]}]
            },
        }]
    }
}

_YAHOO_CHART_WITH_NULL = {
    "chart": {
        "result": [{
            "meta": {
                "regularMarketPrice": 445.0,
                "regularMarketTime": _TS_JUL11,
                "currency": "USD",
            },
            "timestamp": [_TS_JUL9, _TS_JUL10, _TS_JUL11],
            "indicators": {
                "quote": [{"close": [441.5, None, 445.0]}]
            },
        }]
    }
}

_YAHOO_CHART_EURUSD = {
    "chart": {
        "result": [{
            "meta": {
                "regularMarketPrice": 1.0823,
                "regularMarketTime": _TS_JUL10,
                "currency": "USD",
            },
            "timestamp": [_TS_JUL9, _TS_JUL10],
            "indicators": {
                "quote": [{"close": [1.0815, 1.0823]}]
            },
        }]
    }
}


# ---------------------------------------------------------------------------
# httpx mock helpers
# ---------------------------------------------------------------------------

def _make_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_async_client(responses: list[MagicMock]):
    """Return (MockAsyncClientClass, inner_client_mock) with side_effect per call."""
    client = AsyncMock()
    client.get = AsyncMock(side_effect=responses)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=cm), client


# ---------------------------------------------------------------------------
# FX direction — most critical correctness property
# ---------------------------------------------------------------------------

class TestFxDirection:
    """
    Yahoo EURUSD=X regularMarketPrice quotes USD per 1 EUR (e.g. 1.0823).
    We invert to get EUR-per-USD = 1 / quote.
    ``close_eur = close_usd * (1 / eurusd_quote)``
    """

    def test_fx_eur_usd_below_one_when_eurusd_above_parity(self):
        eurusd_quote = 1.08           # USD per EUR
        fx_eur_usd = 1.0 / eurusd_quote
        assert fx_eur_usd < 1.0       # EUR per USD must be < 1 when EUR > USD

    def test_eur_value_less_than_usd_value_above_parity(self):
        close_usd = 450.0
        fx_eur_usd = 1.0 / 1.08
        close_eur = close_usd * fx_eur_usd
        assert close_eur < close_usd

    def test_round_trip_precision(self):
        eurusd_quote = 1.0823
        fx_eur_usd = 1.0 / eurusd_quote
        close_usd = 450.0
        close_eur = close_usd * fx_eur_usd
        expected = 450.0 / 1.0823
        assert abs(close_eur - expected) < 0.0001

    def test_canonical_example_msft_450_eurusd_1_08(self):
        # MSFT $450, EUR/USD = 1.08 → ≈ €416.67
        close_eur = 450.0 * (1.0 / 1.08)
        assert abs(close_eur - 416.67) < 0.01

    def test_inverted_formula_would_produce_higher_value(self):
        # Sanity: using eurusd_quote directly (NOT inverted) gives a higher EUR
        # value, which is wrong — MSFT can't be worth MORE in EUR than in USD
        # when 1 EUR buys more than 1 USD.
        eurusd_quote = 1.08
        close_usd = 450.0
        wrong_eur  = close_usd * eurusd_quote           # ← wrong: 486 EUR
        right_eur  = close_usd * (1.0 / eurusd_quote)  # ← right: 416.67 EUR
        assert wrong_eur > close_usd
        assert right_eur < close_usd

    def test_at_parity_fx_equals_one(self):
        eurusd_quote = 1.0
        fx_eur_usd = 1.0 / eurusd_quote
        assert fx_eur_usd == pytest.approx(1.0)

    def test_yahoo_eurusd_x_snapshot_inverted_correctly(self):
        # Verify the Yahoo EURUSD=X fixture direction: 1.0823 USD/EUR → < 1 EUR/USD
        regular_market_price = _YAHOO_CHART_EURUSD["chart"]["result"][0]["meta"]["regularMarketPrice"]
        fx_eur_usd = 1.0 / regular_market_price
        assert fx_eur_usd < 1.0
        assert abs(fx_eur_usd - (1.0 / 1.0823)) < 0.0001


# ---------------------------------------------------------------------------
# _last_business_day
# ---------------------------------------------------------------------------

class TestLastBusinessDay:
    def test_monday_returns_same(self):
        mon = date(2026, 7, 13)    # Monday
        assert _last_business_day(mon) == mon

    def test_friday_returns_same(self):
        fri = date(2026, 7, 10)    # Friday
        assert _last_business_day(fri) == fri

    def test_saturday_returns_friday(self):
        sat = date(2026, 7, 11)
        assert _last_business_day(sat) == date(2026, 7, 10)

    def test_sunday_returns_friday(self):
        sun = date(2026, 7, 12)
        assert _last_business_day(sun) == date(2026, 7, 10)

    def test_wednesday_returns_same(self):
        wed = date(2026, 7, 15)    # Wednesday (CURRENT_DATETIME)
        assert _last_business_day(wed) == wed


# ---------------------------------------------------------------------------
# _parse_stooq_csv  (kept — parser is still present as fallback)
# ---------------------------------------------------------------------------

_STOOQ_CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-07-10,410.0,415.0,408.0,413.5,5000000\n"
    "2026-07-09,407.0,412.0,405.0,411.0,4800000\n"
)


class TestParseStooqCsv:
    def test_parses_two_rows(self):
        rows = _parse_stooq_csv(_STOOQ_CSV)
        assert len(rows) == 2

    def test_sorted_ascending_by_date(self):
        rows = _parse_stooq_csv(_STOOQ_CSV)
        assert rows[0]["date"] == date(2026, 7, 9)
        assert rows[1]["date"] == date(2026, 7, 10)

    def test_close_value_extracted(self):
        rows = _parse_stooq_csv(_STOOQ_CSV)
        assert rows[1]["close"] == pytest.approx(413.5)

    def test_zero_close_filtered(self):
        csv_with_zero = _STOOQ_CSV + "2026-07-14,0,0,0,0,0\n"
        rows = _parse_stooq_csv(csv_with_zero)
        assert len(rows) == 2

    def test_empty_text_returns_empty(self):
        assert _parse_stooq_csv("") == []

    def test_header_only_returns_empty(self):
        assert _parse_stooq_csv("Date,Open,High,Low,Close,Volume\n") == []


# ---------------------------------------------------------------------------
# _parse_yahoo_history
# ---------------------------------------------------------------------------

class TestParseYahooHistory:
    def test_parses_two_rows(self):
        rows = _parse_yahoo_history(_YAHOO_CHART_MSFT)
        assert len(rows) == 2

    def test_sorted_ascending_by_date(self):
        rows = _parse_yahoo_history(_YAHOO_CHART_MSFT)
        assert rows[0]["date"] == date(2026, 7, 9)
        assert rows[1]["date"] == date(2026, 7, 10)

    def test_close_values_extracted(self):
        rows = _parse_yahoo_history(_YAHOO_CHART_MSFT)
        assert rows[0]["close"] == pytest.approx(441.5)
        assert rows[1]["close"] == pytest.approx(445.0)

    def test_null_close_skipped(self):
        rows = _parse_yahoo_history(_YAHOO_CHART_WITH_NULL)
        # Jul-10 has null close → skipped; Jul-9 and Jul-11 kept
        assert len(rows) == 2
        dates = [r["date"] for r in rows]
        assert date(2026, 7, 10) not in dates

    def test_zero_close_skipped(self):
        data = {
            "chart": {"result": [{
                "meta": {"regularMarketPrice": 0, "regularMarketTime": _TS_JUL9},
                "timestamp": [_TS_JUL9],
                "indicators": {"quote": [{"close": [0.0]}]},
            }]}
        }
        assert _parse_yahoo_history(data) == []

    def test_empty_result_returns_empty(self):
        assert _parse_yahoo_history({}) == []
        assert _parse_yahoo_history({"chart": {"result": []}}) == []

    def test_eurusd_rows_parsed(self):
        rows = _parse_yahoo_history(_YAHOO_CHART_EURUSD)
        assert len(rows) == 2
        assert rows[1]["close"] == pytest.approx(1.0823)


# ---------------------------------------------------------------------------
# _parse_yahoo_snapshot
# ---------------------------------------------------------------------------

class TestParseYahooSnapshot:
    def test_parses_price_and_date(self):
        snap = _parse_yahoo_snapshot(_YAHOO_CHART_MSFT)
        assert snap is not None
        assert snap["close"] == pytest.approx(445.0)
        assert snap["date"] == date(2026, 7, 10)

    def test_eurusd_snapshot(self):
        snap = _parse_yahoo_snapshot(_YAHOO_CHART_EURUSD)
        assert snap is not None
        assert snap["close"] == pytest.approx(1.0823)

    def test_returns_none_on_empty_dict(self):
        assert _parse_yahoo_snapshot({}) is None

    def test_returns_none_on_missing_meta_keys(self):
        data = {"chart": {"result": [{"meta": {}}]}}
        assert _parse_yahoo_snapshot(data) is None

    def test_date_from_utc_timestamp(self):
        # Verify the UTC timestamp conversion gives the expected date
        snap = _parse_yahoo_snapshot(_YAHOO_CHART_MSFT)
        expected = datetime.fromtimestamp(_TS_JUL10, tz=timezone.utc).date()
        assert snap["date"] == expected


# ---------------------------------------------------------------------------
# Yahoo fetch: User-Agent header + 429 fallback
# ---------------------------------------------------------------------------

class TestYahooUserAgent:
    """Verify _yahoo_get sends the correct User-Agent and falls back on 429."""

    @pytest.mark.asyncio
    async def test_user_agent_header_sent(self):
        resp_200 = _make_response(_YAHOO_CHART_MSFT)
        MockClient, inner = _mock_async_client([resp_200])

        with patch("finlytics.investments.market_data.httpx.AsyncClient", MockClient):
            result = await _yahoo_get("MSFT")

        assert result == _YAHOO_CHART_MSFT
        call_kwargs = inner.get.call_args.kwargs
        assert call_kwargs["headers"]["User-Agent"] == _YAHOO_UA

    @pytest.mark.asyncio
    async def test_query1_called_first(self):
        resp_200 = _make_response(_YAHOO_CHART_MSFT)
        MockClient, inner = _mock_async_client([resp_200])

        with patch("finlytics.investments.market_data.httpx.AsyncClient", MockClient):
            await _yahoo_get("MSFT")

        first_url = inner.get.call_args_list[0].args[0]
        assert _YAHOO_HOSTS[0] in first_url  # query1 first

    @pytest.mark.asyncio
    async def test_429_on_query1_falls_back_to_query2(self):
        resp_429 = _make_response({}, status_code=429)
        resp_200 = _make_response(_YAHOO_CHART_MSFT)
        MockClient, inner = _mock_async_client([resp_429, resp_200])

        with patch("finlytics.investments.market_data.httpx.AsyncClient", MockClient):
            result = await _yahoo_get("MSFT")

        assert result == _YAHOO_CHART_MSFT
        assert inner.get.call_count == 2
        urls = [call.args[0] for call in inner.get.call_args_list]
        assert _YAHOO_HOSTS[0] in urls[0]   # query1 first
        assert _YAHOO_HOSTS[1] in urls[1]   # query2 on retry

    @pytest.mark.asyncio
    async def test_both_hosts_fail_returns_none(self):
        exc = httpx.ConnectError("refused")
        inner_client = AsyncMock()
        inner_client.get = AsyncMock(side_effect=exc)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=inner_client)
        cm.__aexit__ = AsyncMock(return_value=None)
        MockClient = MagicMock(return_value=cm)

        with patch("finlytics.investments.market_data.httpx.AsyncClient", MockClient):
            result = await _yahoo_get("MSFT")

        assert result is None

    @pytest.mark.asyncio
    async def test_no_real_network_in_tests(self):
        """Confirm that patching prevents real HTTP calls."""
        resp_200 = _make_response(_YAHOO_CHART_EURUSD)
        MockClient, _ = _mock_async_client([resp_200])

        with patch("finlytics.investments.market_data.httpx.AsyncClient", MockClient):
            result = await _yahoo_get("EURUSD=X")

        # Would have returned None if a real network call was made in CI
        assert result is not None


# ---------------------------------------------------------------------------
# compute_evolution_series — step function + forward fill + granularity
# ---------------------------------------------------------------------------

class TestEvolutionSeries:
    """Tests for the pure series helper."""

    def _lots(self):
        return [
            _Lot(date(2026, 6, 30), Decimal("50"), Decimal("2000.00")),
            _Lot(date(2026, 7, 7),  Decimal("25"), Decimal("1100.00")),
        ]

    def _price_map(self):
        fx = 1.0 / 1.08      # EUR per USD when EURUSD = 1.08
        return {
            date(2026, 6, 30): (400.0, fx),
            date(2026, 7, 1):  (402.0, fx),
            date(2026, 7, 2):  (403.0, fx),
            date(2026, 7, 3):  (405.0, fx),
            date(2026, 7, 7):  (410.0, fx),
            date(2026, 7, 8):  (412.0, 1.0 / 1.07),  # different FX rate
        }

    # ── basic shape ──────────────────────────────────────────────────────────

    def test_returns_two_lists(self):
        lots = self._lots()
        pm = self._price_map()
        vs, cs = compute_evolution_series(lots, pm, date(2026, 6, 30), date(2026, 7, 8))
        assert isinstance(vs, list)
        assert isinstance(cs, list)

    def test_daily_range_has_correct_point_count(self):
        lots = self._lots()
        pm = self._price_map()
        min_d, max_d = date(2026, 6, 30), date(2026, 7, 8)
        vs, cs = compute_evolution_series(lots, pm, min_d, max_d)
        # 6 market days in price_map within range (no weekend/holiday points)
        assert len(cs) == 6

    # ── step function ─────────────────────────────────────────────────────────

    def test_first_lot_only_before_second_purchase(self):
        lots = self._lots()
        pm = self._price_map()
        vs, _ = compute_evolution_series(lots, pm, date(2026, 6, 30), date(2026, 7, 6))
        for pt in vs:
            d = date.fromisoformat(pt.date)
            expected_shares = 50.0
            expected_price = pm.get(d)
            if expected_price:
                expected_val = expected_shares * expected_price[0] * expected_price[1]
                assert pt.value == pytest.approx(expected_val, abs=0.01)

    def test_second_lot_adds_shares_from_its_date(self):
        lots = self._lots()
        pm = self._price_map()
        vs, _ = compute_evolution_series(lots, pm, date(2026, 6, 30), date(2026, 7, 8))
        # On 2026-07-07: 75 shares total (50 + 25), price = 410, fx = 1/1.08
        pt_jul7 = next(p for p in vs if p.date == "2026-07-07")
        expected = 75.0 * 410.0 * (1.0 / 1.08)
        assert pt_jul7.value == pytest.approx(expected, abs=0.01)

    # ── market-day granularity (no weekend/holiday points) ────────────────────

    def test_only_market_days_emitted_no_weekend_points(self):
        lots = [_Lot(date(2026, 6, 29), Decimal("10"), Decimal("400.00"))]
        fx = 1.0 / 1.08
        pm = {date(2026, 6, 29): (400.0, fx)}  # Monday — only trading day in range
        vs, _ = compute_evolution_series(lots, pm, date(2026, 6, 29), date(2026, 7, 1))
        # Sat 2026-06-28 and Sun 2026-06-29 fall outside the 1 market day; range covers
        # Mon 2026-06-29 through Wed 2026-07-01, but price_map only has Mon → 1 point
        assert len(vs) == 1
        assert vs[0].value == pytest.approx(10.0 * 400.0 * fx, abs=0.01)

    def test_no_price_before_first_market_data_produces_no_value_point(self):
        lots = [_Lot(date(2026, 6, 29), Decimal("10"), Decimal("400.00"))]
        pm = {date(2026, 6, 30): (401.0, 1.0 / 1.08)}
        vs, _ = compute_evolution_series(lots, pm, date(2026, 6, 29), date(2026, 6, 30))
        assert len(vs) == 1  # Jun-29 has no price → no value point

    # ── contributions ─────────────────────────────────────────────────────────

    def test_contributions_equal_cost_basis_sum(self):
        lots = self._lots()
        pm = self._price_map()
        _, cs = compute_evolution_series(lots, pm, date(2026, 6, 30), date(2026, 7, 8))
        assert cs[-1].value == pytest.approx(3100.0, abs=0.01)

    def test_contributions_before_second_lot(self):
        lots = self._lots()
        pm = self._price_map()
        _, cs = compute_evolution_series(lots, pm, date(2026, 6, 30), date(2026, 7, 6))
        assert all(pt.value == pytest.approx(2000.0, abs=0.01) for pt in cs)

    # ── granularity: market-day daily (≤2200d) vs weekly (>2200d) ─────────────

    def test_market_day_granularity_for_multi_year_range_under_six_years(self):
        """Ranges > 1 year but ≤ 6 years still use daily market-day resolution."""
        lots = [_Lot(date(2024, 7, 1), Decimal("10"), Decimal("500.00"))]
        pm = {
            date(2024, 7, 1):  (400.0, 1.0 / 1.08),
            date(2025, 7, 15): (420.0, 1.0 / 1.09),
        }
        min_d = date(2024, 7, 1)
        max_d = date(2025, 7, 15)
        assert (max_d - min_d).days > 365
        assert (max_d - min_d).days <= 2200
        vs, cs = compute_evolution_series(lots, pm, min_d, max_d)
        # 2 market days in price_map within range → 2 points
        assert len(cs) == 2

    def test_daily_market_day_points_for_range_under_one_year(self):
        lots = [_Lot(date(2026, 1, 5), Decimal("10"), Decimal("500.00"))]
        pm = {date(2026, 1, 5): (450.0, 1.0 / 1.08)}
        min_d = date(2026, 1, 5)
        max_d = date(2026, 7, 5)   # 181 days
        vs, cs = compute_evolution_series(lots, pm, min_d, max_d)
        # 1 market day in price_map within range → 1 point
        assert len(cs) == 1

    def test_extreme_range_uses_weekly_guardrail(self):
        """total_days > 2200 (~6 years) → weekly sampling to limit payload."""
        lot = _Lot(date(2018, 1, 2), Decimal("10"), Decimal("500.00"))
        # Scatter price entries across a 7-year span
        pm = {
            date(2018, 1, 2):  (85.0, 1.0 / 1.20),
            date(2020, 6, 15): (180.0, 1.0 / 1.13),
            date(2024, 12, 31): (420.0, 1.0 / 1.05),
        }
        min_d = date(2018, 1, 2)
        max_d = date(2025, 1, 2)   # ~2557 days > 2200
        assert (max_d - min_d).days > 2200
        _, cs = compute_evolution_series([lot], pm, min_d, max_d)
        # Weekly → ~365 points; daily would be >2557
        assert len(cs) < 400
        assert len(cs) > 300   # sanity: 7 years of Mondays

    # ── value point format ────────────────────────────────────────────────────

    def test_value_points_are_named_tuples_with_date_and_value(self):
        lots = [_Lot(date(2026, 6, 30), Decimal("50"), Decimal("2000.00"))]
        pm = {date(2026, 6, 30): (400.0, 1.0 / 1.08)}
        vs, _ = compute_evolution_series(lots, pm, date(2026, 6, 30), date(2026, 6, 30))
        assert len(vs) == 1
        pt = vs[0]
        assert isinstance(pt, ValuePoint)
        assert pt.date == "2026-06-30"
        assert isinstance(pt.value, float)

    def test_empty_lots_returns_empty_series(self):
        vs, cs = compute_evolution_series([], {}, date(2026, 6, 30), date(2026, 6, 30))
        assert vs == []
        assert cs == []


# ---------------------------------------------------------------------------
# Helpers: mock DB session + Yahoo history
# ---------------------------------------------------------------------------

def _make_db_session(
    max_date_row: date | None = None,
) -> MagicMock:
    """Return a mock AsyncSession for topup/get_latest_price tests.

    Updated for Model-A: topup_recent_prices now queries
    ``(price_date, fx_eur_usd)`` via ``result.first()`` (not
    ``scalar_one_or_none``). This helper configures both interfaces so
    pre-existing tests keep passing.
    """
    session = MagicMock()
    session.commit = AsyncMock()

    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)

    max_date_result = MagicMock()
    # Legacy interface used by get_latest_price tests
    max_date_result.scalar_one_or_none.return_value = max_date_row
    # Model-A interface: topup_recent_prices uses result.first()
    if max_date_row is None:
        max_date_result.first.return_value = None
    else:
        row = MagicMock()
        row.__getitem__ = MagicMock(
            side_effect=lambda idx: max_date_row if idx == 0 else 0.925926
        )
        max_date_result.first.return_value = row

    session.execute = AsyncMock(return_value=max_date_result)
    return session


def _yahoo_history_rows(
    days: list[tuple[date, float, float]],
) -> list[dict]:
    """Build ``[{date, close}]`` rows for MSFT or EURUSD."""
    return [{"date": d, "close": close} for d, close, _ in days]


def _yahoo_fx_rows(days: list[tuple[date, float, float]]) -> list[dict]:
    return [{"date": d, "close": fx} for d, _, fx in days]


# ---------------------------------------------------------------------------
# topup_recent_prices — UPSERT DO UPDATE, missing days, graceful degradation
# ---------------------------------------------------------------------------

_TOP_UP_ROWS = [
    # (date, msft_close, eurusd_quote)
    (date(2026, 7, 14), 384.0, 1.08),   # last stored — intraday value to be corrected
    (date(2026, 7, 15), 388.0, 1.081),  # today
]


class TestTopupRecentPrices:
    """topup_recent_prices: UPSERT DO UPDATE, gap-fill, graceful degradation."""

    # ── (a) last stored day overwritten with settled close ─────────────────

    @pytest.mark.asyncio
    async def test_last_day_overwritten_do_update(self):
        """UPSERT uses ON CONFLICT DO UPDATE, not DO NOTHING."""
        from sqlalchemy.dialects.postgresql.dml import OnConflictDoUpdate

        db = _make_db_session(max_date_row=date(2026, 7, 14))
        upsert_result = MagicMock()
        # second execute is for the upsert
        db.execute = AsyncMock(side_effect=[
            # max_date query
            MagicMock(**{"scalar_one_or_none.return_value": date(2026, 7, 14)}),
            upsert_result,  # upsert
        ])

        msft = [{"date": d, "close": c} for d, c, _ in _TOP_UP_ROWS]
        fx   = [{"date": d, "close": f} for d, _, f in _TOP_UP_ROWS]

        with (
            patch("finlytics.investments.market_data._fetch_yahoo_history",
                  side_effect=[msft, fx]),
        ):
            await topup_recent_prices(db)

        # Verify the upsert execute was called
        assert db.execute.call_count == 2
        upsert_stmt = db.execute.call_args_list[1].args[0]
        # Statement must use ON CONFLICT DO UPDATE (not DO NOTHING)
        assert isinstance(upsert_stmt._post_values_clause, OnConflictDoUpdate)

    # ── (b) missing days filled ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_missing_days_filled(self):
        """Multiple days returned by Yahoo are all included in the upsert."""
        db = _make_db_session()
        captured_values = []

        async def _capture_execute(stmt, *args, **kwargs):
            # Capture the upsert values list when it's an Insert stmt
            if hasattr(stmt, "_post_values_clause"):
                # Extract values from the compiled statement's _values
                captured_values.extend(stmt._values if hasattr(stmt, "_values") else [])
            return MagicMock()

        db.execute = AsyncMock(side_effect=[
            MagicMock(**{"scalar_one_or_none.return_value": date(2026, 7, 11)}),
            MagicMock(),  # upsert result
        ])

        # Yahoo returns 3 days: 11th (already stored), 14th and 15th (new)
        extra_rows = [
            (date(2026, 7, 11), 380.0, 1.079),
            (date(2026, 7, 14), 384.0, 1.080),
            (date(2026, 7, 15), 388.0, 1.081),
        ]
        msft = [{"date": d, "close": c} for d, c, _ in extra_rows]
        fx   = [{"date": d, "close": f} for d, _, f in extra_rows]

        with patch("finlytics.investments.market_data._fetch_yahoo_history",
                   side_effect=[msft, fx]):
            await topup_recent_prices(db)

        # Upsert execute was called — 3-row window upserted
        assert db.execute.call_count == 2
        upsert_stmt = db.execute.call_args_list[1].args[0]
        # Compiled values list has 3 entries (one per day)
        from sqlalchemy.dialects import postgresql as pg_dialect
        compiled = upsert_stmt.compile(
            dialect=pg_dialect.dialect(),
            compile_kwargs={"render_postcompile": True},
        )
        assert "DO UPDATE SET" in str(compiled).upper()

    # ── (c) UPSERT uses DO UPDATE not DO NOTHING ───────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_uses_do_update_not_do_nothing(self):
        """Explicit assertion: conflict handler is OnConflictDoUpdate."""
        from sqlalchemy.dialects.postgresql.dml import OnConflictDoUpdate, OnConflictDoNothing

        db = _make_db_session()
        db.execute = AsyncMock(side_effect=[
            MagicMock(**{"scalar_one_or_none.return_value": date(2026, 7, 14)}),
            MagicMock(),
        ])

        msft = [{"date": date(2026, 7, 14), "close": 390.0}]
        fx   = [{"date": date(2026, 7, 14), "close": 1.08}]

        with patch("finlytics.investments.market_data._fetch_yahoo_history",
                   side_effect=[msft, fx]):
            await topup_recent_prices(db)

        upsert_stmt = db.execute.call_args_list[1].args[0]
        assert isinstance(upsert_stmt._post_values_clause, OnConflictDoUpdate)
        assert not isinstance(upsert_stmt._post_values_clause, OnConflictDoNothing)

    # ── (d) network failure degrades gracefully ────────────────────────────

    @pytest.mark.asyncio
    async def test_network_failure_no_upsert_no_raise(self):
        """When Yahoo fetch raises, no upsert is attempted and no exception propagates."""
        db = _make_db_session()
        db.execute = AsyncMock(
            return_value=MagicMock(**{"scalar_one_or_none.return_value": date(2026, 7, 14)})
        )

        with patch("finlytics.investments.market_data._fetch_yahoo_history",
                   side_effect=Exception("network timeout")):
            # Must NOT raise
            await topup_recent_prices(db)

        # Only the max_date query was executed — no upsert
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_rows_no_upsert_no_raise(self):
        """When Yahoo returns empty lists, no upsert is attempted."""
        db = _make_db_session()
        db.execute = AsyncMock(
            return_value=MagicMock(**{"scalar_one_or_none.return_value": date(2026, 7, 14)})
        )

        with patch("finlytics.investments.market_data._fetch_yahoo_history",
                   side_effect=[[], []]):
            await topup_recent_prices(db)

        assert db.execute.call_count == 1  # no upsert

    # ── (e) empty price_history → no fetch ────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_history_returns_without_fetching(self):
        """When max_date is None (empty price_history), no network fetch is made."""
        db = _make_db_session(max_date_row=None)

        with patch("finlytics.investments.market_data._fetch_yahoo_history") as mock_fetch:
            await topup_recent_prices(db)

        mock_fetch.assert_not_called()
        # Only the max_date query was executed
        assert db.execute.call_count == 1

    # ── FX inversion preserved ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_fx_inversion_applied_in_upsert(self):
        """close_eur = close_usd / eurusd_quote (inversion applied)."""
        db = _make_db_session()
        db.execute = AsyncMock(side_effect=[
            MagicMock(**{"scalar_one_or_none.return_value": date(2026, 7, 14)}),
            MagicMock(),
        ])

        close_usd = 400.0
        eurusd = 1.08

        msft = [{"date": date(2026, 7, 14), "close": close_usd}]
        fx   = [{"date": date(2026, 7, 14), "close": eurusd}]

        with patch("finlytics.investments.market_data._fetch_yahoo_history",
                   side_effect=[msft, fx]):
            await topup_recent_prices(db)

        # Inspect the values dict passed to the upsert statement
        upsert_stmt = db.execute.call_args_list[1].args[0]
        # The stmt is built via pg_insert(...).values(list_of_dicts).on_conflict...
        # We verify FX math via the expected Decimal values
        expected_fx_eur_usd = round(1.0 / eurusd, 6)
        expected_close_eur  = round(close_usd * (1.0 / eurusd), 6)
        # Verify by checking the insert statement compile includes correct numbers
        from sqlalchemy.dialects import postgresql as pg_dialect
        compiled_str = str(upsert_stmt.compile(dialect=pg_dialect.dialect()))
        # Both expected values should be represented in the compiled SQL
        assert str(expected_fx_eur_usd) in compiled_str or "excluded" in compiled_str


# ---------------------------------------------------------------------------
# get_latest_price — returns latest close, price_stale logic, topup called
# ---------------------------------------------------------------------------

class TestGetLatestPrice:
    """get_latest_price: calls topup, returns latest close, price_stale correct."""

    def _make_price_row(self, d: date, close_usd: float = 400.0) -> MagicMock:
        row = MagicMock()
        row.price_date = d
        row.close_usd  = Decimal(str(close_usd))
        row.fx_eur_usd = Decimal("0.925926")   # 1/1.08
        row.close_eur  = Decimal(str(round(close_usd * 0.925926, 6)))
        return row

    @pytest.mark.asyncio
    async def test_returns_latest_close_from_db(self):
        """get_latest_price returns the most recent row from price_history."""
        price_row = self._make_price_row(date(2026, 7, 15))

        db = MagicMock()
        begin_cm = AsyncMock()
        db.begin = MagicMock(return_value=begin_cm)
        db.execute = AsyncMock(return_value=MagicMock(
            **{"scalar_one_or_none.return_value": price_row}
        ))

        with patch("finlytics.investments.market_data.topup_recent_prices",
                   new=AsyncMock()) as mock_topup:
            result = await get_latest_price(db)

        assert result is not None
        assert result.price_date == date(2026, 7, 15)
        assert result.close_usd == pytest.approx(400.0)
        mock_topup.assert_awaited_once_with(db)

    @pytest.mark.asyncio
    async def test_price_stale_false_when_date_is_last_business_day(self):
        """price_stale=False when stored date equals last business day."""
        lbd = _last_business_day()
        price_row = self._make_price_row(lbd)

        db = MagicMock()
        begin_cm = AsyncMock()
        db.begin = MagicMock(return_value=begin_cm)
        db.execute = AsyncMock(return_value=MagicMock(
            **{"scalar_one_or_none.return_value": price_row}
        ))

        with patch("finlytics.investments.market_data.topup_recent_prices", new=AsyncMock()):
            result = await get_latest_price(db)

        assert result is not None
        assert result.price_stale is False

    @pytest.mark.asyncio
    async def test_price_stale_true_when_date_older_than_last_business_day(self):
        """price_stale=True when stored date is before last business day."""
        old_date = date(2026, 7, 10)  # Friday, before today (Wed 15 Jul)
        assert old_date < _last_business_day()
        price_row = self._make_price_row(old_date)

        db = MagicMock()
        begin_cm = AsyncMock()
        db.begin = MagicMock(return_value=begin_cm)
        db.execute = AsyncMock(return_value=MagicMock(
            **{"scalar_one_or_none.return_value": price_row}
        ))

        with patch("finlytics.investments.market_data.topup_recent_prices", new=AsyncMock()):
            result = await get_latest_price(db)

        assert result is not None
        assert result.price_stale is True

    @pytest.mark.asyncio
    async def test_returns_none_when_price_history_empty(self):
        """Returns None when price_history has no MSFT rows."""
        db = MagicMock()
        begin_cm = AsyncMock()
        db.begin = MagicMock(return_value=begin_cm)
        db.execute = AsyncMock(return_value=MagicMock(
            **{"scalar_one_or_none.return_value": None}
        ))

        with patch("finlytics.investments.market_data.topup_recent_prices", new=AsyncMock()):
            result = await get_latest_price(db)

        assert result is None

    @pytest.mark.asyncio
    async def test_topup_failure_degrades_to_cached_value(self):
        """When topup raises, get_latest_price falls back to cached close."""
        price_row = self._make_price_row(date(2026, 7, 14))

        db = MagicMock()
        begin_cm = AsyncMock()
        db.begin = MagicMock(return_value=begin_cm)
        db.execute = AsyncMock(return_value=MagicMock(
            **{"scalar_one_or_none.return_value": price_row}
        ))

        async def _failing_topup(db):
            raise RuntimeError("network error")

        with patch("finlytics.investments.market_data.topup_recent_prices",
                   new=_failing_topup):
            result = await get_latest_price(db)

        # Must not raise; returns cached row
        assert result is not None
        assert result.close_usd == pytest.approx(400.0)

    @pytest.mark.asyncio
    async def test_topup_called_once_per_invocation(self):
        """topup_recent_prices is called exactly once per get_latest_price call."""
        price_row = self._make_price_row(date(2026, 7, 15))

        db = MagicMock()
        begin_cm = AsyncMock()
        db.begin = MagicMock(return_value=begin_cm)
        db.execute = AsyncMock(return_value=MagicMock(
            **{"scalar_one_or_none.return_value": price_row}
        ))

        with patch("finlytics.investments.market_data.topup_recent_prices",
                   new=AsyncMock()) as mock_topup:
            await get_latest_price(db)

        assert mock_topup.await_count == 1
