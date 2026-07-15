"""Tests for DB-backed portfolio cache (24-hour freshness).

Coverage:
  * _serialize_portfolio / _deserialize_portfolio round-trip.
  * _deserialize_portfolio handles None performance and monthly_returns with int keys.
  * get_portfolio — fresh cache: Indexa NOT called, result from cache.
  * get_portfolio — cache miss: Indexa called, new DB row added.
  * get_portfolio — stale cache: stale data returned immediately,
    BackgroundTasks.add_task called, Indexa NOT called synchronously,
    cache_stale=True in result.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.investments.base import (
    NormalizedDrawdown,
    NormalizedHolding,
    NormalizedMonthlyReturnRow,
    NormalizedPerformance,
    NormalizedPortfolio,
    NormalizedReturns,
    NormalizedValuePoint,
)
from finlytics.investments.service import (
    _CACHE_MAX_AGE,
    _deserialize_portfolio,
    _serialize_portfolio,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_portfolio(*, with_monthly: bool = False) -> NormalizedPortfolio:
    monthly = (
        [
            NormalizedMonthlyReturnRow(
                year=2024,
                months_pct={8: 0.0348, 9: 0.0145},
                months_eur={8: 200.0, 9: 150.0},
                total_pct=0.0499,
                total_eur=350.0,
                benchmark_pct=0.03,
            )
        ]
        if with_monthly
        else []
    )
    return NormalizedPortfolio(
        holdings=[
            NormalizedHolding(
                name="iShares MSCI World",
                ticker="IWDA",
                asset_class="equity",
                units=10.0,
                current_value=1000.0,
                cost_basis=900.0,
                gain_loss=100.0,
                gain_loss_pct=0.1111,
            )
        ],
        total_value=1000.0,
        total_invested=900.0,
        total_gain_loss=100.0,
        performance=NormalizedPerformance(
            total_value=1000.0,
            returns=NormalizedReturns(pl=100.0, invested=900.0, twr_annual=0.08),
            value_series=[NormalizedValuePoint("2024-08-31", 1000.0)],
            monthly_returns=monthly,
            drawdown=NormalizedDrawdown(
                max_drawdown=-0.05,
                max_drawdown_eur=-50.0,
                start_date="2024-01-01",
                end_date="2024-03-31",
            ),
        ),
    )


def _make_connection(conn_id: int = 1, token_enc: str = "enc-tok") -> MagicMock:
    conn = MagicMock()
    conn.id = conn_id
    conn.plugin_id = "indexa-capital"
    conn.status = "active"
    conn.token_enc = token_enc
    conn.account_label_masked = "PBK•••Z5"
    conn.last_synced_at = None
    return conn


def _make_db(connections: list, cache_payload) -> MagicMock:
    """Build a mock AsyncSession.

    cache_payload: dict (fresh/stale cache) or None (cache miss).
    """
    conn_result = MagicMock()
    conn_result.scalars.return_value.all.return_value = connections

    cache_result = MagicMock()
    cache_result.scalar_one_or_none.return_value = cache_payload

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[conn_result, cache_result])
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    begin_cm = AsyncMock()
    mock_db.begin = MagicMock(return_value=begin_cm)
    return mock_db


# ── Serialisation round-trip ──────────────────────────────────────────────────


def test_serialize_deserialize_roundtrip_basic():
    """serialize → deserialize recovers the same portfolio (basic fields)."""
    p = _make_portfolio()
    data = _serialize_portfolio(p)
    r = _deserialize_portfolio(data)

    assert r.total_value == p.total_value
    assert r.total_invested == p.total_invested
    assert r.total_gain_loss == p.total_gain_loss
    assert len(r.holdings) == 1
    h = r.holdings[0]
    assert h.name == "iShares MSCI World"
    assert h.ticker == "IWDA"
    assert h.current_value == pytest.approx(1000.0)
    assert h.gain_loss_pct == pytest.approx(0.1111)
    assert r.performance is not None
    assert r.performance.returns.pl == pytest.approx(100.0)
    assert r.performance.returns.twr_annual == pytest.approx(0.08)


def test_serialize_deserialize_monthly_returns_int_keys():
    """months_pct/months_eur keys are restored as int after JSON round-trip."""
    p = _make_portfolio(with_monthly=True)
    data = _serialize_portfolio(p)
    r = _deserialize_portfolio(data)

    assert r.performance is not None
    assert len(r.performance.monthly_returns) == 1
    row = r.performance.monthly_returns[0]
    assert row.year == 2024
    # JSON round-trip converts int keys to str; deserializer must convert back.
    assert 8 in row.months_pct, "month 8 key must be int, not '8'"
    assert 9 in row.months_pct
    assert row.months_pct[8] == pytest.approx(0.0348)
    assert row.months_eur[9] == pytest.approx(150.0)


def test_serialize_deserialize_none_performance():
    """Portfolio with performance=None survives the round-trip."""
    p = NormalizedPortfolio(
        holdings=[],
        total_value=0.0,
        total_invested=None,
        total_gain_loss=None,
        performance=None,
    )
    r = _deserialize_portfolio(_serialize_portfolio(p))
    assert r.performance is None
    assert r.total_invested is None


def test_serialize_deserialize_drawdown():
    """NormalizedDrawdown is preserved through the round-trip."""
    p = _make_portfolio()
    r = _deserialize_portfolio(_serialize_portfolio(p))
    assert r.performance is not None
    assert r.performance.drawdown is not None
    assert r.performance.drawdown.max_drawdown == pytest.approx(-0.05)
    assert r.performance.drawdown.start_date == "2024-01-01"


# ── Cache hit (fresh) — no API call ──────────────────────────────────────────


async def test_cache_hit_fresh_no_api_call():
    """Fresh DB cache (age < 24h): Indexa NOT called, result served from cache."""
    from finlytics.investments import service as svc

    portfolio = _make_portfolio()
    fresh_ts = datetime.now(timezone.utc) - timedelta(seconds=_CACHE_MAX_AGE / 2)

    mock_cache_row = MagicMock()
    mock_cache_row.payload = _serialize_portfolio(portfolio)
    mock_cache_row.fetched_at = fresh_ts

    mock_db = _make_db([_make_connection()], mock_cache_row)

    mock_api = AsyncMock(side_effect=AssertionError("live API must not be called for fresh cache"))
    mock_validate = AsyncMock(side_effect=AssertionError("validate_token must not be called for fresh cache"))

    with (
        patch("finlytics.investments.service.decrypt_token", return_value="plain"),
        patch.object(svc._PROVIDERS["indexa-capital"], "get_portfolio", new=mock_api),
        patch.object(svc._PROVIDERS["indexa-capital"], "validate_token", new=mock_validate),
    ):
        result = await svc.get_portfolio(user_id=1, db=mock_db)

    mock_api.assert_not_called()
    mock_validate.assert_not_called()
    assert result.total_value == pytest.approx(1000.0)
    assert result.cache_stale is False
    assert result.cached_at is not None  # freshness timestamp populated


# ── Cache miss — fetch + store ────────────────────────────────────────────────


async def test_cache_miss_fetches_live_and_adds_db_row():
    """No cache row: Indexa called, new InvestmentPortfolioCache row added to DB."""
    from finlytics.investments import service as svc
    from finlytics.investments.base import DiscoveredAccount, ValidationResult

    portfolio = _make_portfolio()
    mock_db = _make_db([_make_connection()], None)  # None = cache miss

    validation = ValidationResult(
        valid=True,
        accounts=[DiscoveredAccount("PBKLBYZ5", "mutual", "active")],
    )

    mock_api = AsyncMock(return_value=portfolio)

    with (
        patch("finlytics.investments.service.decrypt_token", return_value="plain"),
        patch.object(svc._PROVIDERS["indexa-capital"], "validate_token", new=AsyncMock(return_value=validation)),
        patch.object(svc._PROVIDERS["indexa-capital"], "get_portfolio", new=mock_api),
    ):
        result = await svc.get_portfolio(user_id=1, db=mock_db)

    mock_api.assert_called_once()
    # DB row was added (INSERT for cache miss)
    mock_db.add.assert_called_once()
    # Session was committed (cache row + last_synced_at)
    mock_db.commit.assert_called_once()
    assert result.total_value == pytest.approx(1000.0)
    # No cache metadata on first (live) fetch
    assert result.cache_stale is False


# ── Cache stale — return immediately + schedule background refresh ─────────────


async def test_stale_cache_returns_stale_and_schedules_background_refresh():
    """Stale cache (> 24h): stale data returned immediately, BackgroundTask scheduled,
    live API NOT called synchronously, cache_stale=True in response."""
    from fastapi import BackgroundTasks

    from finlytics.investments import service as svc

    portfolio = _make_portfolio()
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=_CACHE_MAX_AGE + 300)

    mock_cache_row = MagicMock()
    mock_cache_row.payload = _serialize_portfolio(portfolio)
    mock_cache_row.fetched_at = stale_ts

    mock_db = _make_db([_make_connection()], mock_cache_row)

    bg = BackgroundTasks()

    mock_api = AsyncMock(side_effect=AssertionError("live API must not be called for stale cache"))
    mock_validate = AsyncMock(side_effect=AssertionError("validate must not be called for stale cache"))

    # Ensure connection is not already in-flight
    svc._refresh_in_flight.discard(1)

    with (
        patch("finlytics.investments.service.decrypt_token", return_value="plain"),
        patch.object(svc._PROVIDERS["indexa-capital"], "get_portfolio", new=mock_api),
        patch.object(svc._PROVIDERS["indexa-capital"], "validate_token", new=mock_validate),
    ):
        result = await svc.get_portfolio(user_id=1, db=mock_db, background_tasks=bg)

    # Live API NOT called (stale path returns cached data synchronously)
    mock_api.assert_not_called()
    mock_validate.assert_not_called()

    # Stale data returned immediately
    assert result.total_value == pytest.approx(1000.0)
    assert result.cache_stale is True
    assert result.cached_at is not None  # set to stale timestamp

    # One background refresh task was scheduled
    assert len(bg.tasks) == 1, "Expected exactly one background refresh task"


async def test_stale_in_flight_guard_prevents_duplicate_task():
    """When a background refresh is already in-flight, no second task is scheduled."""
    from fastapi import BackgroundTasks

    from finlytics.investments import service as svc

    portfolio = _make_portfolio()
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=_CACHE_MAX_AGE + 300)

    mock_cache_row = MagicMock()
    mock_cache_row.payload = _serialize_portfolio(portfolio)
    mock_cache_row.fetched_at = stale_ts

    mock_db = _make_db([_make_connection()], mock_cache_row)

    bg = BackgroundTasks()

    # Mark connection 1 as already in-flight
    svc._refresh_in_flight.add(1)
    try:
        with patch("finlytics.investments.service.decrypt_token", return_value="plain"):
            result = await svc.get_portfolio(user_id=1, db=mock_db, background_tasks=bg)

        # Still returns stale data
        assert result.cache_stale is True
        # But NO new background task (already in-flight)
        assert len(bg.tasks) == 0, "Should not schedule a second task when one is in-flight"
    finally:
        svc._refresh_in_flight.discard(1)
