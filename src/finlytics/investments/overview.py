"""The combined investments overview, shared by the API and the assistant.

It used to live inside the ``/combined-overview`` endpoint, and the assistant's
``get_investment_overview`` tool reached it by calling that endpoint function
with a stand-in user and a throwaway ``BackgroundTasks``. A service both of them
call keeps the chat reading the same figures as the page, without depending on
how FastAPI happens to inject the endpoint's arguments.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.schemas import (
    AssetClassAllocationItem,
    CombinedOverviewOut,
    InvestmentPortfolioOut,
    ProviderAllocationItem,
    ProviderCardOut,
)
from finlytics.db.models import EsppLot, InvestmentConnection
from finlytics.db.queries import HOLDING_STATUSES
from finlytics.investments import service as inv_service
from finlytics.investments.crypto import EncryptionNotConfiguredError
from finlytics.investments.market_data import LatestPriceRow, get_latest_price

log = logging.getLogger(__name__)

__all__ = ["build_combined_overview"]

_PROVIDER_LABELS: dict[str, str] = {
    "indexa": "Indexa Capital",
    "fidelity": "Fidelity ESPP",
}

# English fallbacks only: the SPA translates `asset_class` itself
# (frontend/src/investments/assetClass.ts), so these never reach a Spanish UI.
_ASSET_CLASS_LABELS: dict[str, str] = {
    "equity": "Equity",
    "fixed_income": "Fixed income",
    "cash": "Cash",
    "espp_stock": "ESPP stock",
    "other": "Other",
    "mixed": "Mixed",
}


def _empty_overview() -> CombinedOverviewOut:
    """Zero-state overview returned when no active connections exist."""
    return CombinedOverviewOut(
        total_value_eur=0.0,
        total_invested_eur=None,
        total_gain_loss_eur=None,
        total_gain_loss_pct=None,
        by_provider=[],
        by_asset_class=[],
        providers=[],
    )


async def build_combined_overview(
    *,
    user_id: int,
    db: AsyncSession,
    background_tasks: BackgroundTasks | None = None,
) -> CombinedOverviewOut:
    """Aggregate every connected provider into one overview.

    Merges Indexa Capital (24h-cached portfolio) and Fidelity ESPP (lots + latest
    price) into the KPI strip, the provider and asset-class allocations and one
    card per provider.

    A provider that cannot be valued keeps its card, with null values, but is
    left out of the totals and the allocations so the percentages still sum to
    100. Whenever that happens ``partial`` is set, so the caller can say the
    total is incomplete instead of presenting it as the whole.

    ``background_tasks`` lets a stale Indexa cache schedule its refresh; without
    it the cached figures are still returned, but nothing refreshes them.

    Raises ``EncryptionNotConfiguredError`` when an Indexa token cannot be
    decrypted: that is a server misconfiguration, not a degraded provider.
    """
    rows = (
        await db.execute(
            select(InvestmentConnection).where(
                InvestmentConnection.user_id == user_id,
                InvestmentConnection.status.in_(HOLDING_STATUSES),
            )
        )
    ).scalars().all()

    if not rows:
        return _empty_overview()

    active_conns = [c for c in rows if c.status == "active"]
    plugin_ids = {c.plugin_id for c in active_conns}
    has_indexa = any(c.plugin_id == "indexa-capital" for c in rows)
    has_fidelity = "fidelity-espp" in plugin_ids

    lots: Sequence[EsppLot] = []
    if has_fidelity:
        fidelity_conn = next(
            (c for c in active_conns if c.plugin_id == "fidelity-espp"), None
        )
        if fidelity_conn is not None:
            lots = (
                await db.execute(
                    select(EsppLot).where(EsppLot.connection_id == fidelity_conn.id)
                )
            ).scalars().all()
        else:
            has_fidelity = False

    # get_latest_price opens its own db.begin(), which the autobegun
    # transaction above would make raise.
    await db.commit()

    fidelity_price: LatestPriceRow | None = None
    if has_fidelity:
        try:
            fidelity_price = await get_latest_price(db)
        except Exception as exc:  # one provider must not blank the page
            log.warning(
                "combined_overview: get_latest_price failed (degraded): %s", exc, exc_info=True
            )

    # Through the 24h DB cache — never bypass it.
    indexa_portfolio: InvestmentPortfolioOut | None = None
    if has_indexa:
        try:
            indexa_portfolio = await inv_service.get_portfolio(
                user_id=user_id, db=db, background_tasks=background_tasks
            )
        except EncryptionNotConfiguredError:
            raise
        except Exception as exc:  # one provider must not blank the page
            log.warning(
                "combined_overview: Indexa portfolio fetch failed (degraded): %s",
                exc,
                exc_info=True,
            )

    # value_eur is None when the provider could not be valued.
    provider_rows: list[dict] = []
    partial = False

    if has_indexa:
        # last_updated is None when not a single account could be read: the
        # value is unknown, and 0.0 would pass for a real, empty portfolio.
        if indexa_portfolio is not None and indexa_portfolio.last_updated is not None:
            iv: float | None = indexa_portfolio.total_value
            ii: float | None = indexa_portfolio.total_invested
            ig: float | None = indexa_portfolio.total_gain_loss
            partial = indexa_portfolio.accounts_unavailable > 0
        else:
            iv = ii = ig = None
            partial = True
        provider_rows.append({
            "provider_id": "indexa",
            "plugin_id": "indexa-capital",
            "name": "Indexa Capital",
            "icon": "🏦",
            "value_eur": iv,
            "invested_eur": ii,
            "gain_loss_eur": ig,
        })

    if has_fidelity:
        total_shares = sum(float(lot.shares) for lot in lots)
        invested_eur = sum(float(lot.cost_basis) for lot in lots)

        fv: float | None = None
        fg: float | None = None
        if fidelity_price is not None and total_shares > 0:
            fv = total_shares * fidelity_price.close_usd * fidelity_price.fx_eur_usd
            fg = fv - invested_eur
        elif total_shares > 0:
            partial = True

        provider_rows.append({
            "provider_id": "fidelity",
            "plugin_id": "fidelity-espp",
            "name": "Fidelity ESPP",
            "icon": "📊",
            "value_eur": fv,
            "invested_eur": invested_eur if total_shares > 0 else None,
            "gain_loss_eur": fg,
        })

    # Totals only count providers with a known current value.
    total_value = sum(r["value_eur"] for r in provider_rows if r["value_eur"] is not None)
    invested_contributors = [
        r["invested_eur"]
        for r in provider_rows
        if r["value_eur"] is not None and r["invested_eur"] is not None
    ]
    gain_contributors = [
        r["gain_loss_eur"]
        for r in provider_rows
        if r["gain_loss_eur"] is not None
    ]

    total_invested: float | None = sum(invested_contributors) if invested_contributors else None
    total_gain_loss: float | None = sum(gain_contributors) if gain_contributors else None
    total_gain_loss_pct: float | None = None
    if total_gain_loss is not None and total_invested and total_invested > 0:
        total_gain_loss_pct = round(total_gain_loss / total_invested * 100.0, 4)

    # A donut needs real numbers, so an unvalued provider is left out of it.
    by_provider: list[ProviderAllocationItem] = []
    for r in provider_rows:
        if r["value_eur"] is not None:
            pct = round(r["value_eur"] / total_value * 100.0, 2) if total_value > 0 else 0.0
            by_provider.append(ProviderAllocationItem(
                provider=r["provider_id"],
                label=_PROVIDER_LABELS.get(r["provider_id"], r["name"]),
                value_eur=round(r["value_eur"], 2),
                pct=pct,
            ))

    asset_class_values: dict[str, float] = {}
    if indexa_portfolio is not None:
        for h in indexa_portfolio.holdings:
            asset_class_values[h.asset_class] = (
                asset_class_values.get(h.asset_class, 0.0) + h.current_value
            )
    fidelity_row = next((r for r in provider_rows if r["provider_id"] == "fidelity"), None)
    if fidelity_row is not None and fidelity_row["value_eur"] is not None:
        asset_class_values["espp_stock"] = (
            asset_class_values.get("espp_stock", 0.0) + fidelity_row["value_eur"]
        )

    by_asset_class: list[AssetClassAllocationItem] = [
        AssetClassAllocationItem(
            asset_class=ac,
            label=_ASSET_CLASS_LABELS.get(ac, ac),
            value_eur=round(v, 2),
            pct=round(v / total_value * 100.0, 2) if total_value > 0 else 0.0,
        )
        for ac, v in sorted(asset_class_values.items(), key=lambda x: -x[1])
    ]

    providers: list[ProviderCardOut] = []
    for r in provider_rows:
        gl = r["gain_loss_eur"]
        ii_r = r.get("invested_eur")
        gain_pct: float | None = None
        if gl is not None and ii_r and ii_r > 0:
            gain_pct = round(gl / ii_r * 100.0, 4)
        providers.append(ProviderCardOut(
            id=r["plugin_id"],
            name=r["name"],
            icon=r["icon"],
            value_eur=round(r["value_eur"], 2) if r["value_eur"] is not None else None,
            gain_loss_eur=round(gl, 2) if gl is not None else None,
            gain_loss_pct=gain_pct,
            route=f"/investments/{r['plugin_id']}",
        ))

    return CombinedOverviewOut(
        total_value_eur=round(total_value, 2),
        total_invested_eur=round(total_invested, 2) if total_invested is not None else None,
        total_gain_loss_eur=round(total_gain_loss, 2) if total_gain_loss is not None else None,
        total_gain_loss_pct=total_gain_loss_pct,
        by_provider=by_provider,
        by_asset_class=by_asset_class,
        providers=providers,
        partial=partial,
    )
