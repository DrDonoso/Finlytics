"""Indexa Capital investment provider.

Calls three read-only Indexa GET endpoints:
  - GET /users/me                              → token validation + account discovery
  - GET /accounts/{acc}/fiscal-results         → holdings list
  - GET /accounts/{acc}/performance            → totals, value series, returns

Security (Romanoff §4):
  - HTTPS + TLS verify=True enforced.
  - Explicit timeouts (10 s connect / 30 s read).
  - follow_redirects=False to prevent X-AUTH-TOKEN leaking to redirects.
  - Token NEVER written to any log.
  - Only GET calls.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import httpx

from finlytics.investments.base import (
    DiscoveredAccount,
    InvestmentProvider,
    NormalizedCashInvested,
    NormalizedContributionEvent,
    NormalizedDrawdown,
    NormalizedHolding,
    NormalizedMonthlyReturnRow,
    NormalizedPerformance,
    NormalizedPortfolio,
    NormalizedReturns,
    NormalizedValuePoint,
    ValidationResult,
)

log = logging.getLogger(__name__)

_BASE_URL = "https://api.indexacapital.com"
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

_ASSET_CLASS_MAP: dict[str, str] = {
    "cash": "cash",
    "money_market": "cash",
}


class IndexaAuthError(Exception):
    """Token rejected by Indexa (HTTP 401 or 403)."""


class IndexaConnectionError(Exception):
    """Network / timeout / unexpected HTTP error from Indexa."""


def _map_asset_class(raw: str) -> str:
    """Normalize Indexa asset_class string to our internal enum value."""
    if raw.startswith("equity"):
        return "equity"
    if raw.startswith("fixed_income"):
        return "fixed_income"
    return _ASSET_CLASS_MAP.get(raw, "other")


def _fmt_date(yyyymmdd: str | int) -> str:
    """Convert YYYYMMDD (string or int) to YYYY-MM-DD."""
    s = str(yyyymmdd)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _make_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={"X-AUTH-TOKEN": token},
        verify=True,
        timeout=_TIMEOUT,
        follow_redirects=False,
    )


async def _get(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    """Execute a GET request; raise domain errors on failure."""
    try:
        resp = await client.get(path)
    except httpx.TimeoutException as exc:
        raise IndexaConnectionError("Indexa request timed out") from exc
    except httpx.RequestError as exc:
        raise IndexaConnectionError("Indexa network error") from exc

    if resp.status_code in (401, 403):
        raise IndexaAuthError(f"Indexa returned HTTP {resp.status_code}")
    if not resp.is_success:
        raise IndexaConnectionError(f"Indexa returned HTTP {resp.status_code}")
    return resp.json()


def _compute_monthly_returns(
    history: dict,
    benchmark: dict | list,
    total_amounts_raw: dict,
    net_amounts_raw: dict,
) -> list[NormalizedMonthlyReturnRow]:
    """Compute per-month / per-year return rows from Indexa history + benchmark.

    Args:
        history: YYYY-MM-DD → cumulative TWR multiplier (base 1.0 at inception).
        benchmark: Real Indexa shape is a DICT keyed by date string
            (e.g. {"2024-08-31": {"date": ..., "benchmark_percentage_return": str|int}}).
            Also accepts a list of such dicts for backwards compatibility.
        total_amounts_raw: YYYYMMDD → portfolio value (from return.total_amounts).
        net_amounts_raw: YYYYMMDD → net cumulative contributions (top-level net_amounts).
    """
    if not history:
        return []

    # Convert daily series to YYYY-MM-DD keyed dicts for lookup
    tv: dict[str, float] = {
        _fmt_date(str(k)): float(v)
        for k, v in total_amounts_raw.items()
        if len(str(k)) == 8
    }
    na: dict[str, float] = {
        _fmt_date(str(k)): float(v)
        for k, v in net_amounts_raw.items()
        if len(str(k)) == 8
    }

    # Benchmark lookup by date — real Indexa returns a dict keyed by date;
    # also accept a list defensively (test mocks, legacy shapes).
    if isinstance(benchmark, dict):
        bm_entries = benchmark.values()
    else:
        bm_entries = benchmark or []
    bm_by_date: dict[str, float] = {
        e.get("date", ""): float(e.get("benchmark_percentage_return") or 0)
        for e in bm_entries
        if isinstance(e, dict)
    }

    sorted_hist = sorted(history.keys())
    monthly_rows: list[tuple] = []  # (year, month, pct, eur|None, bm_pct|None)

    prev_twr = 1.0
    prev_date: str | None = None

    for date_str in sorted_hist:
        twr = float(history[date_str])
        year = int(date_str[:4])
        month = int(date_str[5:7])

        # Monthly TWR return
        if prev_date is None:
            monthly_pct = twr - 1.0
        else:
            monthly_pct = (twr / prev_twr) - 1.0 if prev_twr else 0.0

        # Monthly EUR P&L = (value_end − value_start) − (net_end − net_start)
        val_end = tv.get(date_str)
        val_start = tv.get(prev_date) if prev_date else 0.0
        na_end = na.get(date_str, 0.0)
        na_start = na.get(prev_date, 0.0) if prev_date else 0.0

        monthly_eur: float | None = (
            (val_end - (val_start or 0.0)) - (na_end - na_start)
            if val_end is not None and val_start is not None
            else None
        )

        bm_pct: float | None = bm_by_date.get(date_str)

        monthly_rows.append((year, month, monthly_pct, monthly_eur, bm_pct))
        prev_twr = twr
        prev_date = date_str

    # Group by year
    by_year: dict[int, list] = defaultdict(list)
    for row in monthly_rows:
        by_year[row[0]].append(row)

    result: list[NormalizedMonthlyReturnRow] = []
    for year in sorted(by_year.keys()):
        rows_y = by_year[year]

        months_pct = {r[1]: r[2] for r in rows_y}
        months_eur = {r[1]: r[3] for r in rows_y}

        # Compound annual TWR
        total_pct = 1.0
        for r in rows_y:
            total_pct *= 1.0 + r[2]
        total_pct -= 1.0

        # Sum annual EUR P&L
        eur_vals = [r[3] for r in rows_y if r[3] is not None]
        total_eur: float | None = sum(eur_vals) if eur_vals else None

        # Compound annual benchmark
        bm_vals = [r[4] for r in rows_y if r[4] is not None]
        if bm_vals:
            bm_total = 1.0
            for b in bm_vals:
                bm_total *= 1.0 + b
            benchmark_pct: float | None = bm_total - 1.0
        else:
            benchmark_pct = None

        result.append(
            NormalizedMonthlyReturnRow(
                year=year,
                months_pct=months_pct,
                months_eur=months_eur,
                total_pct=total_pct,
                total_eur=total_eur,
                benchmark_pct=benchmark_pct,
            )
        )

    return result


def _derive_contribution_events(raw_net_amounts: dict) -> list[NormalizedContributionEvent]:
    """Derive individual contribution/withdrawal events from cumulative net_amounts.

    net_amounts: YYYYMMDD → cumulative net invested (EUR, float).
    Deltas between consecutive entries are individual movements.
    Positive delta → contribution; negative delta → withdrawal.
    First entry: if value == 0.0 (account-open marker), it is skipped; otherwise
    it is treated as the initial contribution (delta = value itself).
    Zero deltas are always skipped.
    """
    sorted_pairs = sorted(
        ((str(k), float(v)) for k, v in raw_net_amounts.items() if len(str(k)) == 8),
        key=lambda x: x[0],
    )

    events: list[NormalizedContributionEvent] = []
    prev_cumulative: float | None = None

    for yyyymmdd, cumulative in sorted_pairs:
        if prev_cumulative is None:
            # First entry
            amount = round(cumulative, 2)
            if amount == 0.0:
                # Account-open marker — skip, but anchor prev_cumulative
                prev_cumulative = cumulative
                continue
        else:
            amount = round(cumulative - prev_cumulative, 2)

        if amount == 0.0:
            prev_cumulative = cumulative
            continue

        events.append(NormalizedContributionEvent(
            date=_fmt_date(yyyymmdd),
            amount=amount,
            cumulative=round(cumulative, 2),
            type="contribution" if amount > 0 else "withdrawal",
        ))
        prev_cumulative = cumulative

    return events


async def _fetch_performance(
    client: httpx.AsyncClient, account_number: str
) -> NormalizedPerformance:
    """Inner helper shared by get_portfolio and get_performance."""
    data = await _get(client, f"/accounts/{account_number}/performance")

    ret = data.get("return", {})

    # FIX 1: total_amounts is nested at data["return"]["total_amounts"] (not top-level).
    # Keys are YYYYMMDD — reformat to YYYY-MM-DD.
    raw_total_amounts: dict = ret.get("total_amounts", {})
    total_amounts: dict[str, float] = {
        _fmt_date(str(k)): float(v)
        for k, v in raw_total_amounts.items()
        if len(str(k)) == 8
    }

    portfolios: list[dict] = data.get("portfolios", [])

    value_series = [
        NormalizedValuePoint(date=d, value=v)
        for d, v in sorted(total_amounts.items())
    ]

    # FIX 2: portfolios are newest-first — use [0] for the latest snapshot
    cash_invested: NormalizedCashInvested | None = None
    latest: dict | None = None
    if portfolios:
        latest = portfolios[0]
        cash_invested = NormalizedCashInvested(
            cash_amount=float(latest.get("cash_amount") or 0),
            instruments_amount=float(latest.get("instruments_amount") or 0),
            instruments_cost=float(latest.get("instruments_cost") or 0),
            total_amount=float(latest.get("total_amount") or 0),
        )

    # FIX 3: total_value — authoritative from portfolios[0].total_amount.
    # Fallback chain: portfolios[0] → last entry in total_amounts → top-level field.
    top_level_tv = data.get("total_amount")
    total_value = float(latest.get("total_amount") or 0) if latest else 0.0

    if total_value == 0.0 and total_amounts:
        total_value = float(total_amounts[max(total_amounts.keys())] or 0)

    if total_value == 0.0 and top_level_tv:
        total_value = float(top_level_tv)

    if not top_level_tv:
        log.debug(
            "Indexa: top-level total_amount absent for account %s; "
            "derived total_value=%.2f from portfolios/series fallback",
            account_number, total_value,
        )

    # ADD: contributions_series from top-level net_amounts (YYYYMMDD keys)
    raw_net_amounts: dict = data.get("net_amounts", {})
    contributions_series = [
        NormalizedValuePoint(date=_fmt_date(str(k)), value=float(v))
        for k, v in sorted(raw_net_amounts.items())
        if len(str(k)) == 8
    ]

    # Derive individual contribution/withdrawal events from the cumulative net_amounts
    contribution_events = _derive_contribution_events(raw_net_amounts)

    # ADD: monthly returns matrix from history + benchmark
    # Real Indexa /performance returns benchmark as a dict keyed by date.
    history: dict = data.get("history", {})
    benchmark = data.get("benchmark") or {}
    monthly_returns = _compute_monthly_returns(
        history, benchmark, raw_total_amounts, raw_net_amounts
    )

    # ADD: max drawdown
    drawdown: NormalizedDrawdown | None = None
    drawdown_data = data.get("drawdowns")
    if drawdown_data:
        try:
            drawdown = NormalizedDrawdown(
                max_drawdown=float(drawdown_data.get("max_drawdown", 0)),
                max_drawdown_eur=float(drawdown_data.get("max_drawdown_EUR", 0)),
                start_date=_fmt_date(drawdown_data["start_date_max_drawdown"]),
                end_date=_fmt_date(drawdown_data["end_date_max_drawdown"]),
            )
        except (KeyError, ValueError, TypeError):
            pass

    return NormalizedPerformance(
        total_value=total_value,
        returns=NormalizedReturns(
            twr_annual=ret.get("time_return_annual"),
            twr_total=ret.get("time_return"),
            twr_last_week=ret.get("time_return_last_week"),
            twr_last_month=ret.get("time_return_last_month"),
            twr_last_year=ret.get("time_return_last_year"),
            money_return=ret.get("money_return"),
            money_return_annual=ret.get("money_return_annual"),
            volatility=data.get("volatility"),
            xirr=ret.get("XIRR"),
            pl=ret.get("pl"),
            invested=ret.get("investment"),
            aportaciones=ret.get("inflows"),
            retenciones=ret.get("tax_outflows"),
            rentabilidad_eur=ret.get("pl"),
            rentabilidad_pct=ret.get("money_return"),
            sharpe_ratio=data.get("sharpe_ratio"),
        ),
        value_series=value_series,
        contributions_series=contributions_series,
        contribution_events=contribution_events,
        monthly_returns=monthly_returns,
        drawdown=drawdown,
        cash_invested=cash_invested,
    )


class IndexaProvider(InvestmentProvider):
    plugin_id = "indexa-capital"

    async def validate_token(self, token: str) -> ValidationResult:
        async with _make_client(token) as client:
            data = await _get(client, "/users/me")

        accounts = [
            DiscoveredAccount(
                account_number=acc["account_number"],
                account_type=acc.get("type", ""),
                account_status=acc.get("status", "active"),
            )
            for acc in data.get("accounts", [])
        ]
        log.info("Indexa token validated — %d account(s) discovered", len(accounts))
        return ValidationResult(valid=True, accounts=accounts)

    async def get_portfolio(
        self, token: str, account_numbers: list[str]
    ) -> NormalizedPortfolio:
        holdings: list[NormalizedHolding] = []
        total_value = 0.0
        total_invested: float | None = None
        total_gain_loss: float | None = None
        aggregated_perf: NormalizedPerformance | None = None

        async with _make_client(token) as client:
            for acc_num in account_numbers:
                holdings_before = len(holdings)

                # Holdings from fiscal-results — aggregate by ISIN (BUG B fix)
                fiscal = await _get(client, f"/accounts/{acc_num}/fiscal-results")
                by_isin: dict[str, dict[str, Any]] = {}
                for fr in fiscal.get("fiscal_results", []):
                    instrument = fr.get("instrument", {})
                    key = instrument.get("identifier") or instrument.get("name", "")
                    if key not in by_isin:
                        by_isin[key] = {
                            "instrument": instrument,
                            "amount": 0.0,
                            "cost_amount": 0.0,
                            "titles": 0.0,
                            "profit_loss": 0.0,
                        }
                    by_isin[key]["amount"] += float(fr.get("amount") or 0)
                    by_isin[key]["cost_amount"] += float(fr.get("cost_amount") or 0)
                    by_isin[key]["titles"] += float(fr.get("titles") or 0)
                    by_isin[key]["profit_loss"] += float(fr.get("profit_loss") or 0)

                for agg in sorted(by_isin.values(), key=lambda x: x["amount"], reverse=True):
                    instrument = agg["instrument"]
                    cost = agg["cost_amount"]
                    pl = agg["profit_loss"]
                    gain_pct = (pl / cost) if cost else None
                    holdings.append(
                        NormalizedHolding(
                            name=instrument.get("name", ""),
                            ticker=instrument.get("identifier"),
                            asset_class=_map_asset_class(
                                instrument.get("asset_class", "")
                            ),
                            units=agg["titles"] or None,
                            current_value=agg["amount"],
                            cost_basis=cost or None,
                            gain_loss=pl,
                            gain_loss_pct=gain_pct,
                        )
                    )

                # Totals + series from performance
                perf = await _fetch_performance(client, acc_num)

                # Step 4 fallback: if total_value still 0, sum this account's holdings
                acc_total = perf.total_value
                if acc_total == 0.0:
                    acc_total = sum(
                        h.current_value for h in holdings[holdings_before:]
                    )
                total_value += acc_total

                if perf.returns.invested is not None:
                    total_invested = (total_invested or 0.0) + perf.returns.invested
                if perf.returns.pl is not None:
                    total_gain_loss = (total_gain_loss or 0.0) + perf.returns.pl

                if aggregated_perf is None:
                    aggregated_perf = perf
                else:
                    # Merge value_series by date (sum)
                    by_date: dict[str, float] = {
                        vp.date: vp.value for vp in aggregated_perf.value_series
                    }
                    for vp in perf.value_series:
                        by_date[vp.date] = by_date.get(vp.date, 0.0) + vp.value
                    aggregated_perf.value_series = [
                        NormalizedValuePoint(date=d, value=v)
                        for d, v in sorted(by_date.items())
                    ]
                    # Merge cash_invested (sum)
                    if perf.cash_invested and aggregated_perf.cash_invested:
                        ci_a = aggregated_perf.cash_invested
                        ci_b = perf.cash_invested
                        aggregated_perf.cash_invested = NormalizedCashInvested(
                            cash_amount=ci_a.cash_amount + ci_b.cash_amount,
                            instruments_amount=ci_a.instruments_amount + ci_b.instruments_amount,
                            instruments_cost=ci_a.instruments_cost + ci_b.instruments_cost,
                            total_amount=ci_a.total_amount + ci_b.total_amount,
                        )
                    # Merge contribution_events by date (sum deltas, recompute cumulative)
                    ev_by_date: dict[str, float] = {}
                    for ev in aggregated_perf.contribution_events:
                        ev_by_date[ev.date] = ev_by_date.get(ev.date, 0.0) + ev.amount
                    for ev in perf.contribution_events:
                        ev_by_date[ev.date] = ev_by_date.get(ev.date, 0.0) + ev.amount
                    running = 0.0
                    merged_events: list[NormalizedContributionEvent] = []
                    for d, amt in sorted(ev_by_date.items()):
                        amt_r = round(amt, 2)
                        if amt_r == 0.0:
                            continue
                        running = round(running + amt_r, 2)
                        merged_events.append(NormalizedContributionEvent(
                            date=d,
                            amount=amt_r,
                            cumulative=running,
                            type="contribution" if amt_r > 0 else "withdrawal",
                        ))
                    aggregated_perf.contribution_events = merged_events
                    # Non-aggregatable: clear for multi-account
                    aggregated_perf.returns.twr_annual = None
                    aggregated_perf.returns.twr_total = None
                    aggregated_perf.returns.twr_last_week = None
                    aggregated_perf.returns.twr_last_month = None
                    aggregated_perf.returns.twr_last_year = None
                    aggregated_perf.returns.volatility = None
                    aggregated_perf.returns.xirr = None
                    # Aggregatable: sum
                    if perf.returns.pl is not None:
                        aggregated_perf.returns.pl = (
                            aggregated_perf.returns.pl or 0.0
                        ) + perf.returns.pl
                    if perf.returns.invested is not None:
                        aggregated_perf.returns.invested = (
                            aggregated_perf.returns.invested or 0.0
                        ) + perf.returns.invested
                    if perf.returns.money_return is not None:
                        aggregated_perf.returns.money_return = (
                            aggregated_perf.returns.money_return or 0.0
                        ) + perf.returns.money_return

        return NormalizedPortfolio(
            holdings=holdings,
            total_value=total_value,
            total_invested=total_invested,
            total_gain_loss=total_gain_loss,
            performance=aggregated_perf,
        )

    async def get_performance(
        self, token: str, account_number: str
    ) -> NormalizedPerformance:
        async with _make_client(token) as client:
            return await _fetch_performance(client, account_number)
