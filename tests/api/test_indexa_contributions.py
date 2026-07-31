"""Comprehensive tests for Indexa contribution_events derivation.

Contract:
  _derive_contribution_events(raw_net_amounts) → list[NormalizedContributionEvent]
  Each event: {date: YYYY-MM-DD, amount: float (signed), cumulative: float, type: str}
  type ∈ {"contribution", "withdrawal"}

Coverage (per task specification):
  TC-1  Correct deltas: series {0, 2000, 4000, 17999.99} → 3 events with exact amounts/cumulatives
  TC-2a First entry = 0.0 skipped (account-open marker)
  TC-2b First entry NON-ZERO emitted as initial contribution
  TC-3  WITHDRAWAL: negative delta → negative amount + type="withdrawal"  ← HEADLINE TEST
  TC-4  Zero delta skipped: date with unchanged net_amounts → no event
  TC-5  Empty net_amounts → empty list, no crash
  TC-6  Multi-account aggregation: same-date deltas summed
  TC-7a Events sorted by date (ASC)
  TC-7b Amounts rounded to cents (2 decimal places)
  TC-8  Partial withdrawal in the middle of a series
  TC-9  Schema validation: ContributionEventOut exposes all contract fields
  TC-10 Cache round-trip: serialize/deserialize preserves contribution_events
  TC-11 End-to-end integration: _fetch_performance + contribution_events in NormalizedPerformance
  TC-12 Multi-account (provider): get_portfolio with two accounts sums same-date deltas
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_perf_data(net_amounts: dict, **extra) -> dict:
    """Build a mock /performance response with the given net_amounts."""
    base = {
        "total_amount": 20000.0,
        "return": {},
        "net_amounts": net_amounts,
        "portfolios": [
            {
                "cash_amount": 0.0,
                "instruments_amount": 20000.0,
                "instruments_cost": 18000.0,
                "total_amount": 20000.0,
            }
        ],
    }
    base.update(extra)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# TC-1  CORRECT DELTAS
# ─────────────────────────────────────────────────────────────────────────────

def test_tc1_derive_amounts_and_cumulatives():
    """TC-1: net_amounts {20240804:0, 20240904:2000, 20241004:4000, 20241231:17999.99}
    → 3 events with amounts [2000, 2000, 13999.99] and cumulatives [2000, 4000, 17999.99].

    The first entry (0.0) is the account-open marker and is skipped.
    """
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 2000.0,
        "20241004": 4000.0,
        "20241231": 17999.99,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3, f"Expected 3 events, got {len(events)}"

    # Evento 1
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)
    assert events[0].type == "contribution"

    # Evento 2
    assert events[1].date == "2024-10-04"
    assert events[1].amount == pytest.approx(2000.0)
    assert events[1].cumulative == pytest.approx(4000.0)
    assert events[1].type == "contribution"

    # Evento 3 — delta grande: 17999.99 − 4000.00 = 13999.99
    assert events[2].date == "2024-12-31"
    assert events[2].amount == pytest.approx(13999.99)
    assert events[2].cumulative == pytest.approx(17999.99)
    assert events[2].type == "contribution"


def test_tc1_integer_net_amount_keys():
    """TC-1 variant: keys may be integers (as Indexa returns in raw form)."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        20240804: 0,
        20240904: 2000,
        20241004: 4000,
        20241231: 17999.99,
    }
    events = _derive_contribution_events(raw)
    assert len(events) == 3
    assert events[2].amount == pytest.approx(13999.99)


# ─────────────────────────────────────────────────────────────────────────────
# TC-2  FIRST ENTRY
# ─────────────────────────────────────────────────────────────────────────────

def test_tc2a_first_entry_zero_skipped():
    """TC-2a: First entry = 0.0 is skipped; generates no events."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {"20240804": 0.0}
    events = _derive_contribution_events(raw)
    assert events == [], "The account-open marker (0.0) must not generate any event"


def test_tc2a_first_entry_zero_then_contributions():
    """TC-2a: Skipping the initial 0.0 does not affect subsequent events."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {"20240804": 0.0, "20240904": 5000.0}
    events = _derive_contribution_events(raw)
    assert len(events) == 1
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(5000.0)
    assert events[0].cumulative == pytest.approx(5000.0)
    assert events[0].type == "contribution"


def test_tc2b_first_entry_nonzero_emitted():
    """TC-2b: The first NON-ZERO entry is emitted as the initial contribution,
    with amount = the accumulated value itself (no prev_cumulative)."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {"20240904": 3000.0, "20241004": 5000.0}
    events = _derive_contribution_events(raw)
    assert len(events) == 2

    # First contribution = the full initial value
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(3000.0)
    assert events[0].cumulative == pytest.approx(3000.0)
    assert events[0].type == "contribution"

    # Second contribution = delta from the first value
    assert events[1].date == "2024-10-04"
    assert events[1].amount == pytest.approx(2000.0)
    assert events[1].cumulative == pytest.approx(5000.0)
    assert events[1].type == "contribution"


# ─────────────────────────────────────────────────────────────────────────────
# TC-3  WITHDRAWAL — HEADLINE TEST
# ─────────────────────────────────────────────────────────────────────────────

def test_tc3_withdrawal_headline_delta_negative():
    """TC-3 HEADLINE: decreasing net_amounts produces a NEGATIVE event with type="withdrawal".

    Series: 0 → 2000 → 4000 → 3500
    Event on 20241104: delta = 3500 − 4000 = −500 → withdrawal.
    """
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 2000.0,
        "20241004": 4000.0,
        "20241104": 3500.0,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3

    withdrawal = events[2]
    assert withdrawal.date == "2024-11-04"
    assert withdrawal.amount == pytest.approx(-500.0), (
        f"Expected withdrawal −500.0, got {withdrawal.amount}"
    )
    assert withdrawal.cumulative == pytest.approx(3500.0), (
        f"Expected cumulative 3500.0 after withdrawal, got {withdrawal.cumulative}"
    )
    assert withdrawal.type == "withdrawal", (
        f"Type must be 'withdrawal' for a negative delta, got {withdrawal.type!r}"
    )


def test_tc3_withdrawal_only_event():
    """TC-3 variant: withdrawal from a portfolio that has only had contributions → type OK."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 10000.0,
        "20241004": 8000.0,   # −2000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 2
    assert events[1].type == "withdrawal"
    assert events[1].amount == pytest.approx(-2000.0)
    assert events[1].cumulative == pytest.approx(8000.0)


def test_tc3_multiple_withdrawals():
    """TC-3 variant: multiple consecutive withdrawals, each with type='withdrawal'."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 10000.0,
        "20241004": 8000.0,    # −2000
        "20241104": 6000.0,    # −2000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3
    assert events[1].type == "withdrawal"
    assert events[1].amount == pytest.approx(-2000.0)
    assert events[1].cumulative == pytest.approx(8000.0)
    assert events[2].type == "withdrawal"
    assert events[2].amount == pytest.approx(-2000.0)
    assert events[2].cumulative == pytest.approx(6000.0)


def test_tc3_withdrawal_followed_by_contribution():
    """TC-3 variant: withdrawal followed by re-contribution — types alternate correctly."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 10000.0,  # contribution
        "20241004": 8000.0,   # withdrawal −2000
        "20241104": 12000.0,  # contribution +4000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3
    assert events[0].type == "contribution"
    assert events[1].type == "withdrawal"
    assert events[2].type == "contribution"
    assert events[2].amount == pytest.approx(4000.0)
    assert events[2].cumulative == pytest.approx(12000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-4  ZERO DELTA SKIPPED
# ─────────────────────────────────────────────────────────────────────────────

def test_tc4_zero_delta_no_event():
    """TC-4: A date with no change in net_amounts produces no event."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 2000.0,
        "20241004": 2000.0,   # delta = 0 → skipped
        "20241104": 5000.0,   # delta = 3000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 2, (
        f"Zero delta must be skipped. Expected 2 events, got {len(events)}"
    )
    dates = [ev.date for ev in events]
    assert "2024-10-04" not in dates, "The date with delta=0 must not appear in any event"
    assert events[0].date == "2024-09-04"
    assert events[1].date == "2024-11-04"
    assert events[1].amount == pytest.approx(3000.0)
    assert events[1].cumulative == pytest.approx(5000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-5  EMPTY NET_AMOUNTS
# ─────────────────────────────────────────────────────────────────────────────

def test_tc5_empty_net_amounts_returns_empty():
    """TC-5: Empty net_amounts → empty list, no crash or exception."""
    from finlytics.investments.indexa import _derive_contribution_events

    events = _derive_contribution_events({})
    assert events == [], "Empty net_amounts must produce an empty list"


def test_tc5_none_equivalent_empty():
    """TC-5 variant: keys with invalid format (length != 8) are ignored, no crash."""
    from finlytics.investments.indexa import _derive_contribution_events

    # Keys with length != 8 must be filtered out
    raw = {"20240": 1000.0, "202408040000": 2000.0}
    events = _derive_contribution_events(raw)
    assert events == [], "Keys with length != 8 must be ignored"


# ─────────────────────────────────────────────────────────────────────────────
# TC-6  MULTI-ACCOUNT AGGREGATION
# ─────────────────────────────────────────────────────────────────────────────

def test_tc6_multi_account_same_date_deltas_summed_via_aggregate():
    """TC-6 via _aggregate (service): two accounts with events on the same date
    → amounts summed, cumulative recalculated.

    Account A: 2024-09-04 +2000, 2024-10-04 +2000
    Account B: 2024-09-04 +3000, 2024-10-04 +1000
    Result: 2024-09-04 +5000 (cumul=5000), 2024-10-04 +3000 (cumul=8000)
    """
    from unittest.mock import MagicMock

    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _aggregate

    perf_a = NormalizedPerformance(
        total_value=20000.0,
        returns=NormalizedReturns(pl=1000.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=2000.0, cumulative=2000.0, type="contribution"),
            NormalizedContributionEvent(date="2024-10-04", amount=2000.0, cumulative=4000.0, type="contribution"),
        ],
    )
    perf_b = NormalizedPerformance(
        total_value=18000.0,
        returns=NormalizedReturns(pl=800.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=3000.0, cumulative=3000.0, type="contribution"),
            NormalizedContributionEvent(date="2024-10-04", amount=1000.0, cumulative=4000.0, type="contribution"),
        ],
    )

    conn_a = MagicMock()
    conn_a.plugin_id = "indexa-capital"
    conn_b = MagicMock()
    conn_b.plugin_id = "indexa-capital"

    portfolio_a = NormalizedPortfolio(
        holdings=[], total_value=20000.0, total_invested=19000.0,
        total_gain_loss=1000.0, performance=perf_a,
    )
    portfolio_b = NormalizedPortfolio(
        holdings=[], total_value=18000.0, total_invested=17200.0,
        total_gain_loss=800.0, performance=perf_b,
    )

    result = _aggregate([(conn_a, portfolio_a), (conn_b, portfolio_b)], total_connections=2)

    events = result.contribution_events
    assert len(events) == 2, f"Expected 2 aggregated events, got {len(events)}"

    ev_by_date = {ev.date: ev for ev in events}

    # 2024-09-04: 2000 + 3000 = 5000
    sep = ev_by_date.get("2024-09-04")
    assert sep is not None, "Must have an event on 2024-09-04"
    assert sep.amount == pytest.approx(5000.0), f"Amount 2024-09-04 expected 5000, got {sep.amount}"
    assert sep.cumulative == pytest.approx(5000.0), f"Cumulative 2024-09-04 expected 5000, got {sep.cumulative}"
    assert sep.type == "contribution"

    # 2024-10-04: 2000 + 1000 = 3000; cumulative = 5000 + 3000 = 8000
    oct_ = ev_by_date.get("2024-10-04")
    assert oct_ is not None, "Must have an event on 2024-10-04"
    assert oct_.amount == pytest.approx(3000.0), f"Amount 2024-10-04 expected 3000, got {oct_.amount}"
    assert oct_.cumulative == pytest.approx(8000.0), f"Cumulative 2024-10-04 expected 8000, got {oct_.cumulative}"
    assert oct_.type == "contribution"


def test_tc6_multi_account_withdrawal_cancels_contribution():
    """TC-6: A withdrawal from account B can partially cancel a contribution from account A.

    Account A: 2024-09-04 +2000
    Account B: 2024-09-04 −500  (withdrawal)
    Result: 2024-09-04 +1500 (contribution)
    """
    from unittest.mock import MagicMock

    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _aggregate

    perf_a = NormalizedPerformance(
        total_value=12000.0,
        returns=NormalizedReturns(pl=500.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=2000.0, cumulative=2000.0, type="contribution"),
        ],
    )
    perf_b = NormalizedPerformance(
        total_value=9500.0,
        returns=NormalizedReturns(pl=300.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=-500.0, cumulative=9500.0, type="withdrawal"),
        ],
    )

    conn_a = MagicMock()
    conn_a.plugin_id = "indexa-capital"
    conn_b = MagicMock()
    conn_b.plugin_id = "indexa-capital"

    portfolio_a = NormalizedPortfolio(holdings=[], total_value=12000.0, total_invested=11500.0,
                                       total_gain_loss=500.0, performance=perf_a)
    portfolio_b = NormalizedPortfolio(holdings=[], total_value=9500.0, total_invested=9200.0,
                                       total_gain_loss=300.0, performance=perf_b)

    result = _aggregate([(conn_a, portfolio_a), (conn_b, portfolio_b)], total_connections=2)

    events = result.contribution_events
    assert len(events) == 1
    assert events[0].amount == pytest.approx(1500.0)  # 2000 + (−500)
    assert events[0].type == "contribution"
    assert events[0].cumulative == pytest.approx(1500.0)


def test_tc6_multi_account_opposite_amounts_produce_zero_skip():
    """TC-6 edge: If the sum of deltas on a date is exactly 0, the event is skipped."""
    from unittest.mock import MagicMock

    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _aggregate

    perf_a = NormalizedPerformance(
        total_value=10000.0,
        returns=NormalizedReturns(pl=0.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=2000.0, cumulative=2000.0, type="contribution"),
        ],
    )
    perf_b = NormalizedPerformance(
        total_value=10000.0,
        returns=NormalizedReturns(pl=0.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=-2000.0, cumulative=8000.0, type="withdrawal"),
        ],
    )

    conn_a = MagicMock()
    conn_a.plugin_id = "indexa-capital"
    conn_b = MagicMock()
    conn_b.plugin_id = "indexa-capital"

    portfolio_a = NormalizedPortfolio(holdings=[], total_value=10000.0, total_invested=10000.0,
                                       total_gain_loss=0.0, performance=perf_a)
    portfolio_b = NormalizedPortfolio(holdings=[], total_value=10000.0, total_invested=10000.0,
                                       total_gain_loss=0.0, performance=perf_b)

    result = _aggregate([(conn_a, portfolio_a), (conn_b, portfolio_b)], total_connections=2)

    # Sum of deltas = 0 → event skipped
    events = result.contribution_events
    assert events == [], (
        f"Opposite deltas that cancel out (sum=0) must be skipped. "
        f"Got: {events}"
    )


async def test_tc6_multi_account_via_provider_get_portfolio():
    """TC-6 via IndexaProvider.get_portfolio: two accounts with the same date
    → contribution_events contains the summed delta with correct cumulative.

    Account 1: net_amounts {20240904: 2000}
    Account 2: net_amounts {20240904: 3000}
    Expected: 1 event on 2024-09-04 with amount=5000, cumulative=5000
    """
    from finlytics.investments.indexa import IndexaProvider

    fiscal_empty = {"fiscal_results": []}

    perf_a = _make_perf_data(
        net_amounts={"20240904": 2000.0},
        total_amount=12000.0,
    )
    perf_b = _make_perf_data(
        net_amounts={"20240904": 3000.0},
        total_amount=10000.0,
    )

    # _get is called in this order:
    # get_portfolio("ACC1"): fiscal_results(ACC1), performance(ACC1)
    # get_portfolio("ACC2"): fiscal_results(ACC2), performance(ACC2)
    side_effects = [fiscal_empty, perf_a, fiscal_empty, perf_b]

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch("finlytics.investments.indexa._get", side_effect=side_effects),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1", "ACC2"])

    perf = portfolio.performance
    assert perf is not None, "performance must be present"
    events = perf.contribution_events
    assert len(events) == 1, f"Expected 1 summed event, got {len(events)}"
    ev = events[0]
    assert ev.date == "2024-09-04"
    assert ev.amount == pytest.approx(5000.0), f"Summed amount expected 5000, got {ev.amount}"
    assert ev.cumulative == pytest.approx(5000.0)
    assert ev.type == "contribution"


# ─────────────────────────────────────────────────────────────────────────────
# TC-7  ORDERING AND ROUNDING
# ─────────────────────────────────────────────────────────────────────────────

def test_tc7a_events_sorted_by_date_ascending():
    """TC-7a: Events are always returned sorted by date ascending."""
    from finlytics.investments.indexa import _derive_contribution_events

    # Dict passed in a different order; the function must sort them
    raw = {
        "20241231": 17999.99,
        "20241004": 4000.0,
        "20240804": 0.0,
        "20240904": 2000.0,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3
    dates = [ev.date for ev in events]
    assert dates == sorted(dates), f"Events are not in ascending order: {dates}"


def test_tc7b_amounts_rounded_to_cents():
    """TC-7b: Amounts are rounded to 2 decimal places (cents)."""
    from finlytics.investments.indexa import _derive_contribution_events

    # 0 → 1999.995 → delta redondeado a 2000.00
    # 1999.995 → 3333.333 → delta = 1333.338 → redondeado a 1333.34
    raw = {
        "20240804": 0.0,
        "20240904": 1999.995,
        "20241004": 3333.333,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 2
    # First: amount = round(1999.995, 2) = 2000.0 (Python banker's rounding)
    assert events[0].amount == pytest.approx(round(1999.995, 2), abs=0.01)
    # Segundo: amount = round(3333.333 - 1999.995, 2)
    expected_delta = round(3333.333 - 1999.995, 2)
    assert events[1].amount == pytest.approx(expected_delta, abs=0.01)
    # Cumulative also rounded
    assert events[1].cumulative == pytest.approx(round(3333.333, 2), abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# TC-8  PARTIAL WITHDRAWAL MID-SERIES
# ─────────────────────────────────────────────────────────────────────────────

def test_tc8_partial_withdrawal_midpoint():
    """TC-8: A mid-series withdrawal does not break correct computation of subsequent events.

    Series: 0 → 5000 → 3000 (−2000) → 8000 (+5000)
    """
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 5000.0,
        "20241004": 3000.0,    # withdrawal −2000
        "20241104": 8000.0,    # contribution +5000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3

    assert events[0].amount == pytest.approx(5000.0)
    assert events[0].type == "contribution"
    assert events[0].cumulative == pytest.approx(5000.0)

    assert events[1].amount == pytest.approx(-2000.0)
    assert events[1].type == "withdrawal"
    assert events[1].cumulative == pytest.approx(3000.0)

    assert events[2].amount == pytest.approx(5000.0)
    assert events[2].type == "contribution"
    assert events[2].cumulative == pytest.approx(8000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-9  SCHEMA VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def test_tc9_schema_contribution_event_out_has_all_fields():
    """TC-9: ContributionEventOut exposes date, amount, cumulative, and type (full contract)."""
    from finlytics.api.schemas import ContributionEventOut

    ev = ContributionEventOut(
        date="2024-09-04",
        amount=2000.0,
        cumulative=2000.0,
        type="contribution",
    )
    assert ev.date == "2024-09-04"
    assert ev.amount == pytest.approx(2000.0)
    assert ev.cumulative == pytest.approx(2000.0)
    assert ev.type == "contribution"


def test_tc9_schema_withdrawal_event():
    """TC-9: ContributionEventOut accepts a negative amount and type='withdrawal'."""
    from finlytics.api.schemas import ContributionEventOut

    ev = ContributionEventOut(
        date="2024-11-04",
        amount=-500.0,
        cumulative=3500.0,
        type="withdrawal",
    )
    assert ev.amount == pytest.approx(-500.0)
    assert ev.cumulative == pytest.approx(3500.0)
    assert ev.type == "withdrawal"


def test_tc9_portfolio_out_schema_exposes_contribution_events():
    """TC-9: InvestmentPortfolioOut includes contribution_events=[] by default."""
    from finlytics.api.schemas import ContributionEventOut, InvestmentPortfolioOut

    out = InvestmentPortfolioOut(
        total_value=0.0,
        currency="EUR",
        holdings=[],
        plugins_connected=0,
    )
    # Must have contribution_events as an empty list by default
    assert hasattr(out, "contribution_events")
    assert isinstance(out.contribution_events, list)
    assert out.contribution_events == []


def test_tc9_portfolio_out_with_events():
    """TC-9: InvestmentPortfolioOut accepts a non-empty contribution_events list."""
    from finlytics.api.schemas import ContributionEventOut, InvestmentPortfolioOut

    ev = ContributionEventOut(
        date="2024-09-04",
        amount=2000.0,
        cumulative=2000.0,
        type="contribution",
    )
    out = InvestmentPortfolioOut(
        total_value=2000.0,
        currency="EUR",
        holdings=[],
        plugins_connected=1,
        contribution_events=[ev],
    )
    assert len(out.contribution_events) == 1
    assert out.contribution_events[0].amount == pytest.approx(2000.0)
    assert out.contribution_events[0].cumulative == pytest.approx(2000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-10  CACHE ROUND-TRIP
# ─────────────────────────────────────────────────────────────────────────────

def test_tc10_cache_round_trip_preserves_contribution_events():
    """TC-10: _serialize_portfolio / _deserialize_portfolio preserves contribution_events
    with all fields (date, amount, cumulative, type)."""
    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _deserialize_portfolio, _serialize_portfolio

    original = NormalizedPortfolio(
        holdings=[],
        total_value=17999.99,
        total_invested=18000.0,
        total_gain_loss=-0.01,
        performance=NormalizedPerformance(
            total_value=17999.99,
            returns=NormalizedReturns(pl=-0.01),
            contribution_events=[
                NormalizedContributionEvent(
                    date="2024-09-04",
                    amount=2000.0,
                    cumulative=2000.0,
                    type="contribution",
                ),
                NormalizedContributionEvent(
                    date="2024-10-04",
                    amount=2000.0,
                    cumulative=4000.0,
                    type="contribution",
                ),
                NormalizedContributionEvent(
                    date="2024-12-31",
                    amount=13999.99,
                    cumulative=17999.99,
                    type="contribution",
                ),
            ],
        ),
    )

    serialized = _serialize_portfolio(original)
    restored = _deserialize_portfolio(serialized)

    assert restored.performance is not None
    events = restored.performance.contribution_events
    assert len(events) == 3, f"Round-trip lost events: expected 3, got {len(events)}"

    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)
    assert events[0].type == "contribution"

    assert events[2].date == "2024-12-31"
    assert events[2].amount == pytest.approx(13999.99)
    assert events[2].cumulative == pytest.approx(17999.99)
    assert events[2].type == "contribution"


def test_tc10_cache_round_trip_withdrawal():
    """TC-10: The cache round-trip preserves withdrawal-type events."""
    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _deserialize_portfolio, _serialize_portfolio

    original = NormalizedPortfolio(
        holdings=[],
        total_value=3500.0,
        total_invested=3500.0,
        total_gain_loss=0.0,
        performance=NormalizedPerformance(
            total_value=3500.0,
            returns=NormalizedReturns(),
            contribution_events=[
                NormalizedContributionEvent(
                    date="2024-09-04",
                    amount=4000.0,
                    cumulative=4000.0,
                    type="contribution",
                ),
                NormalizedContributionEvent(
                    date="2024-11-04",
                    amount=-500.0,
                    cumulative=3500.0,
                    type="withdrawal",
                ),
            ],
        ),
    )

    serialized = _serialize_portfolio(original)
    restored = _deserialize_portfolio(serialized)

    events = restored.performance.contribution_events
    assert len(events) == 2
    withdrawal = events[1]
    assert withdrawal.type == "withdrawal"
    assert withdrawal.amount == pytest.approx(-500.0)
    assert withdrawal.cumulative == pytest.approx(3500.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-11  END-TO-END INTEGRATION (_fetch_performance)
# ─────────────────────────────────────────────────────────────────────────────

async def test_tc11_fetch_performance_returns_contribution_events():
    """TC-11: _fetch_performance with a full net_amounts dict produces contribution_events
    in NormalizedPerformance (real pipeline integration)."""
    from finlytics.investments.indexa import _fetch_performance

    mock_data = _make_perf_data(
        net_amounts={
            "20240804": 0.0,
            "20240904": 2000.0,
            "20241004": 4000.0,
            "20241231": 17999.99,
        }
    )
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert hasattr(result, "contribution_events"), (
        "NormalizedPerformance must have the contribution_events field"
    )
    events = result.contribution_events
    assert len(events) == 3

    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)
    assert events[0].type == "contribution"

    assert events[2].date == "2024-12-31"
    assert events[2].amount == pytest.approx(13999.99)
    assert events[2].cumulative == pytest.approx(17999.99)
    assert events[2].type == "contribution"


async def test_tc11_fetch_performance_withdrawal_in_events():
    """TC-11: _fetch_performance with a withdrawal in net_amounts → contribution_events
    includes the withdrawal event with a negative amount."""
    from finlytics.investments.indexa import _fetch_performance

    mock_data = _make_perf_data(
        net_amounts={
            "20240804": 0.0,
            "20240904": 2000.0,
            "20241004": 4000.0,
            "20241104": 3500.0,   # withdrawal −500
        }
    )
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC_W")

    events = result.contribution_events
    assert len(events) == 3

    withdrawal = events[2]
    assert withdrawal.date == "2024-11-04"
    assert withdrawal.amount == pytest.approx(-500.0), (
        f"CRITICAL: withdrawal must have amount=−500.0, "
        f"got {withdrawal.amount}. The withdrawal type is not represented."
    )
    assert withdrawal.type == "withdrawal", (
        f"CRITICAL: type must be 'withdrawal', got {withdrawal.type!r}"
    )
    assert withdrawal.cumulative == pytest.approx(3500.0)


async def test_tc11_fetch_performance_empty_net_amounts():
    """TC-11: _fetch_performance with empty net_amounts → empty contribution_events."""
    from finlytics.investments.indexa import _fetch_performance

    mock_data = _make_perf_data(net_amounts={})
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC_EMPTY")

    assert result.contribution_events == []


# ─────────────────────────────────────────────────────────────────────────────
# TC-12  MULTI-ACCOUNT (IndexaProvider.get_portfolio)
# ─────────────────────────────────────────────────────────────────────────────

async def test_tc12_provider_get_portfolio_two_accounts_merge_events():
    """TC-12: IndexaProvider.get_portfolio with two accounts →
    same-date contribution_events are summed correctly.

    ACC1: net_amounts {20240804:0, 20241004:2000}
    ACC2: net_amounts {20240804:0, 20241004:3000}
    Expected: [{2024-10-04, amount=5000, cumulative=5000, contribution}]
    """
    from finlytics.investments.indexa import IndexaProvider

    fiscal_empty = {"fiscal_results": []}
    perf_acc1 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20241004": 2000.0},
        total_amount=12000.0,
    )
    perf_acc2 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20241004": 3000.0},
        total_amount=10000.0,
    )

    side_effects = [fiscal_empty, perf_acc1, fiscal_empty, perf_acc2]

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch("finlytics.investments.indexa._get", side_effect=side_effects),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1", "ACC2"])

    assert portfolio.performance is not None
    events = portfolio.performance.contribution_events

    assert len(events) == 1, f"Expected 1 summed event, got {len(events)}: {events}"
    ev = events[0]
    assert ev.date == "2024-10-04"
    assert ev.amount == pytest.approx(5000.0), (
        f"Summed delta expected 5000 (2000+3000), got {ev.amount}"
    )
    assert ev.cumulative == pytest.approx(5000.0)
    assert ev.type == "contribution"


async def test_tc12_provider_two_accounts_different_dates():
    """TC-12 variant: two accounts with different dates → events combined chronologically."""
    from finlytics.investments.indexa import IndexaProvider

    fiscal_empty = {"fiscal_results": []}
    # ACC1: contribution in Sep; ACC2: contribution in Oct
    perf_acc1 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20240904": 2000.0},
        total_amount=12000.0,
    )
    perf_acc2 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20241004": 3000.0},
        total_amount=10000.0,
    )

    side_effects = [fiscal_empty, perf_acc1, fiscal_empty, perf_acc2]

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch("finlytics.investments.indexa._get", side_effect=side_effects),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1", "ACC2"])

    events = portfolio.performance.contribution_events

    assert len(events) == 2, f"Expected 2 events (different dates), got {len(events)}"
    dates = [ev.date for ev in events]
    assert dates == sorted(dates), "Events must be sorted chronologically"

    # Sep: 2000 (ACC1 only), cumulative = 2000
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)

    # Oct: 3000 (ACC2 only), cumulative = 2000 + 3000 = 5000
    assert events[1].date == "2024-10-04"
    assert events[1].amount == pytest.approx(3000.0)
    assert events[1].cumulative == pytest.approx(5000.0)
