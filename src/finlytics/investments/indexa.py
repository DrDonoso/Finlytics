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
from typing import Any

import httpx

from finlytics.investments.base import (
    DiscoveredAccount,
    InvestmentProvider,
    NormalizedCashInvested,
    NormalizedHolding,
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


async def _fetch_performance(
    client: httpx.AsyncClient, account_number: str
) -> NormalizedPerformance:
    """Inner helper shared by get_portfolio and get_performance."""
    data = await _get(client, f"/accounts/{account_number}/performance")

    ret = data.get("return", {})
    total_amounts: dict[str, float] = data.get("total_amounts", {})
    portfolios: list[dict] = data.get("portfolios", [])

    value_series = [
        NormalizedValuePoint(date=d, value=float(v))
        for d, v in sorted(total_amounts.items())
    ]

    cash_invested: NormalizedCashInvested | None = None
    if portfolios:
        latest = portfolios[-1]
        cash_invested = NormalizedCashInvested(
            cash_amount=float(latest.get("cash_amount") or 0),
            instruments_amount=float(latest.get("instruments_amount") or 0),
            instruments_cost=float(latest.get("instruments_cost") or 0),
            total_amount=float(latest.get("total_amount") or 0),
        )

    return NormalizedPerformance(
        total_value=float(data.get("total_amount") or 0),
        returns=NormalizedReturns(
            twr_annual=ret.get("time_return_annual"),
            xirr=ret.get("XIRR"),
            pl=ret.get("pl"),
            invested=ret.get("investment"),
        ),
        value_series=value_series,
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
                # Holdings from fiscal-results
                fiscal = await _get(client, f"/accounts/{acc_num}/fiscal-results")
                for fr in fiscal.get("fiscal_results", []):
                    instrument = fr.get("instrument", {})
                    cost = float(fr.get("cost_amount") or 0)
                    pl = float(fr.get("profit_loss") or 0)
                    gain_pct = (pl / cost) if cost else None
                    holdings.append(
                        NormalizedHolding(
                            name=instrument.get("name", ""),
                            ticker=instrument.get("identifier"),
                            asset_class=_map_asset_class(
                                instrument.get("asset_class", "")
                            ),
                            units=fr.get("titles"),
                            current_value=float(fr.get("amount") or 0),
                            cost_basis=cost or None,
                            gain_loss=pl,
                            gain_loss_pct=gain_pct,
                        )
                    )

                # Totals + series from performance
                perf = await _fetch_performance(client, acc_num)
                total_value += perf.total_value
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
                    # twr_annual/xirr not aggregatable; clear for multi-account
                    aggregated_perf.returns.twr_annual = None
                    aggregated_perf.returns.xirr = None
                    if perf.returns.pl is not None:
                        aggregated_perf.returns.pl = (
                            aggregated_perf.returns.pl or 0.0
                        ) + perf.returns.pl
                    if perf.returns.invested is not None:
                        aggregated_perf.returns.invested = (
                            aggregated_perf.returns.invested or 0.0
                        ) + perf.returns.invested

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
